import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useForm, type UseFormReturn } from "react-hook-form";
import { PersonalityCard } from "../personality-card";
import { TONE_PRESETS } from "@/lib/companion-voice";
import type { AssistantFormValues } from "@/app/settings/page";

function Harness({ initial }: { initial: { tone_preset: string; prompt_seed: string } }) {
  // Construct just enough of AssistantFormValues to satisfy the type — only
  // assistant_identity.tone_preset and assistant_identity.prompt_seed are read by PersonalityCard.
  const form = useForm({
    defaultValues: {
      assistant_identity: { ...initial },
    },
  }) as unknown as UseFormReturn<AssistantFormValues>;
  return <PersonalityCard form={form} />;
}

describe("PersonalityCard", () => {
  it("auto-fills prompt seed when switching from a matching preset", () => {
    render(<Harness initial={{ tone_preset: "warm-curious", prompt_seed: TONE_PRESETS["warm-curious"] }} />);
    fireEvent.click(screen.getByRole("radio", { name: /concise analyst/i }));
    expect(screen.getByTestId("resolved-seed-preview")).toHaveTextContent(/clinical/i);
  });

  it("flips tone_preset to 'custom' when the user types in the override textarea", () => {
    render(<Harness initial={{ tone_preset: "warm-curious", prompt_seed: TONE_PRESETS["warm-curious"] }} />);
    fireEvent.click(screen.getByRole("button", { name: /edit prompt seed directly/i }));
    fireEvent.change(screen.getByLabelText(/^prompt seed$/i), { target: { value: "I am a pirate." } });
    expect(screen.getByRole("radio", { name: /custom/i })).toBeChecked();
  });

  it("shows confirm dialog when switching presets while in custom mode", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<Harness initial={{ tone_preset: "custom", prompt_seed: "Pirate persona" }} />);
    fireEvent.click(screen.getByRole("radio", { name: /warm & curious/i }));
    expect(confirmSpy).toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("auto-promotes tone_preset to 'custom' when legacy custom seed is loaded", async () => {
    // Legacy data: ``tone_preset`` is the default "warm-curious" but
    // ``prompt_seed`` is a user-authored override from the pre-M23 free
    // text UI. The card should normalise ``tone_preset`` to "custom" on
    // mount so the radio, preview, and backend resolver agree.
    render(
      <Harness
        initial={{
          tone_preset: "warm-curious",
          prompt_seed: "Old free-text seed from before M23.",
        }}
      />,
    );
    const customRadio = await screen.findByRole("radio", { name: /custom/i });
    expect(customRadio).toBeChecked();
  });

  it("shows the custom seed in the preview, not the canonical preset", () => {
    render(
      <Harness
        initial={{
          tone_preset: "warm-curious",
          prompt_seed: "Old free-text seed from before M23.",
        }}
      />,
    );
    expect(screen.getByTestId("resolved-seed-preview")).toHaveTextContent(
      "Old free-text seed from before M23.",
    );
  });
});
