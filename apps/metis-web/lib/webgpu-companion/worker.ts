/**
 * WebGPU inference Web Worker for the METIS companion.
 *
 * Runs @huggingface/transformers inside a dedicated worker thread so the main
 * UI thread stays responsive during the ~500 MB model download and
 * token-by-token generation.  The model is cached in the browser's IndexedDB
 * by the library after the first download, so subsequent page loads skip the
 * network transfer.
 *
 * Message protocol  (→ main→worker  ← worker→main):
 *
 *   → { type: "load" }
 *   ← { type: "progress", loaded: number, total: number, pct: number }
 *   ← { type: "ready" }
 *   ← { type: "error", message: string }
 *
 *   → { type: "generate", messages: Array<{ role: string; content: string }> }
 *   ← { type: "token", token: string }
 *   ← { type: "done" }
 *   ← { type: "error", message: string }
 *
 *   → { type: "stop" }   (interrupts current generation gracefully)
 */

// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore – @huggingface/transformers v4 pre-release; types may lag slightly
import {
  pipeline,
  TextStreamer,
  InterruptableStoppingCriteria,
  type TextGenerationPipeline,
} from "@huggingface/transformers";

// Bonsai 1.7B ONNX with 1-bit quantisation (~500 MB cached).  Chosen so the
// companion can run continuously in "always-on" mode — a smaller model plus
// lower GPU pressure means less battery / thermal impact per autonomous event.
// Mirrors the reference implementation at
// https://huggingface.co/spaces/webml-community/bonsai-webgpu
const MODEL_ID = "onnx-community/Bonsai-1.7B-ONNX";

let gen: TextGenerationPipeline | null = null;
const stopper = new InterruptableStoppingCriteria();

type IncomingMessage =
  | { type: "load" }
  | { type: "generate"; messages: Array<{ role: string; content: string }> }
  | { type: "stop" };

self.addEventListener("message", async (e: MessageEvent<IncomingMessage>) => {
  const { type } = e.data;

  // ── load ─────────────────────────────────────────────────────────────────
  if (type === "load") {
    try {
      gen = await pipeline("text-generation", MODEL_ID, {
        dtype: "q1",
        device: "webgpu",
        progress_callback: (info: Record<string, unknown>) => {
          // Only forward meaningful download progress – skip compile/init events
          if (info.status !== "progress_total") return;
          self.postMessage({
            type: "progress",
            loaded: Number(info.loaded ?? 0),
            total: Number(info.total ?? 0),
            pct: Number(info.progress ?? 0),
          });
        },
      });
      self.postMessage({ type: "ready" });
    } catch (err) {
      self.postMessage({ type: "error", message: errorMessage(err) });
      // Keep the worker alive so the main thread can read the error; terminate
      // is handled from the hook side.
    }
    return;
  }

  // ── generate ──────────────────────────────────────────────────────────────
  if (type === "generate") {
    if (!gen) {
      self.postMessage({ type: "error", message: "Model not loaded." });
      return;
    }

    const { messages } = e.data as Extract<IncomingMessage, { type: "generate" }>;
    stopper.reset();

    const streamer = new TextStreamer(gen.tokenizer, {
      skip_prompt: true,
      skip_special_tokens: true,
      callback_function: (token: string) => {
        self.postMessage({ type: "token", token });
      },
    });

    try {
      await gen(messages, {
        max_new_tokens: 512,
        do_sample: false,
        streamer,
        stopping_criteria: stopper,
      });
    } catch (err) {
      // Interrupted stopping criteria throws internally – that's expected;
      // surface actual errors only.
      const msg = errorMessage(err);
      if (!msg.toLowerCase().includes("interrupted")) {
        self.postMessage({ type: "error", message: msg });
      }
    }

    self.postMessage({ type: "done" });
    return;
  }

  // ── stop ──────────────────────────────────────────────────────────────────
  if (type === "stop") {
    stopper.interrupt();
  }
});

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
