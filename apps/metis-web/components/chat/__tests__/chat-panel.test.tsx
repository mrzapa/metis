import { render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "../chat-panel";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; children?: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/components/chat/index-picker-dialog", () => ({
  IndexPickerDialog: () => null,
}));

vi.mock("@/components/chat/model-status-dialog", () => ({
  ModelStatusDialog: () => null,
}));

describe("ChatPanel", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = vi.fn();
      },
    );
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a Heretic shortcut that deep-links to models settings", () => {
    render(<ChatPanel messages={[]} sessionMeta={null} />);

    expect(screen.getByRole("link", { name: "Heretic" })).toHaveAttribute(
      "href",
      "/settings?tab=models&modelsTab=heretic",
    );
  });

  it("renders Forecast mode controls when forecast is the active path", () => {
    render(
      <ChatPanel
        messages={[]}
        sessionMeta={null}
        initialQueryMode="forecast"
        forecastPreflight={{
          ready: true,
          timesfm_available: true,
          covariates_available: true,
          model_id: "google/timesfm-2.5-200m-pytorch",
          max_context: 15360,
          max_horizon: 1000,
          xreg_mode: "xreg + timesfm",
          force_xreg_cpu: true,
          warnings: [],
          install_guidance: [],
        }}
        forecastSchema={{
          file_path: "/tmp/revenue.csv",
          file_name: "revenue.csv",
          delimiter: ",",
          row_count: 12,
          column_count: 3,
          columns: [
            {
              name: "ds",
              detected_type: "timestamp",
              non_null_count: 12,
              unique_count: 12,
              numeric_ratio: 0,
              timestamp_ratio: 1,
              sample_values: ["2026-03-01"],
            },
            {
              name: "y",
              detected_type: "numeric",
              non_null_count: 10,
              unique_count: 10,
              numeric_ratio: 1,
              timestamp_ratio: 0,
              sample_values: ["100"],
            },
            {
              name: "promo",
              detected_type: "numeric",
              non_null_count: 12,
              unique_count: 2,
              numeric_ratio: 1,
              timestamp_ratio: 0,
              sample_values: ["0"],
            },
          ],
          timestamp_candidates: ["ds"],
          numeric_target_candidates: ["y", "promo"],
          suggested_mapping: {
            timestamp_column: "ds",
            target_column: "y",
            dynamic_covariates: ["promo"],
            static_covariates: [],
          },
          validation: {
            valid: true,
            errors: [],
            warnings: [],
            history_row_count: 10,
            future_row_count: 2,
            inferred_horizon: 2,
            resolved_horizon: 2,
            inferred_frequency: "daily",
          },
        }}
        forecastMapping={{
          timestamp_column: "ds",
          target_column: "y",
          dynamic_covariates: ["promo"],
          static_covariates: [],
        }}
        forecastHorizon={2}
      />,
    );

    // Forecast path pill is now exposed in the path toggle alongside
    // Direct / RAG (audit item 15). When a forecast schema is loaded,
    // it should be the active pill.
    const forecastPathButton = screen.getByRole("button", { name: "Forecast" });
    expect(forecastPathButton).toBeInTheDocument();
    expect(forecastPathButton).toHaveAttribute("data-active", "true");
    // Attach button is still visible in the composer for file replacement
    expect(screen.getByRole("button", { name: "Attach time series data" })).toBeInTheDocument();
    // Forecast preflight strip renders automatically when in forecast mode
    expect(screen.getByText("Forecast preflight")).toBeInTheDocument();
    expect(screen.getByText("Forecast ready")).toBeInTheDocument();
    // Column mapping selectors are populated from the provided schema
    expect(screen.getByDisplayValue("ds")).toBeInTheDocument();
    expect(screen.getByDisplayValue("y")).toBeInTheDocument();
  });
});
