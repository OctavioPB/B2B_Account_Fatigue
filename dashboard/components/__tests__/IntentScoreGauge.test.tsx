import { render, screen } from "@testing-library/react";
import { IntentScoreGauge } from "../IntentScoreGauge";

describe("IntentScoreGauge", () => {
  it("renders the score value", () => {
    render(<IntentScoreGauge score={75} confidence={0.82} />);
    expect(screen.getByText("75")).toBeInTheDocument();
  });

  it("renders confidence percentage", () => {
    render(<IntentScoreGauge score={60} confidence={0.9} />);
    expect(screen.getByText(/90%/i)).toBeInTheDocument();
  });

  it("rounds float score in display", () => {
    render(<IntentScoreGauge score={67.4} confidence={0.7} />);
    expect(screen.getByText("67")).toBeInTheDocument();
  });

  it("has an accessible role=img with aria-label", () => {
    render(<IntentScoreGauge score={50} confidence={0.6} />);
    expect(screen.getByRole("img")).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", expect.stringContaining("50"));
  });

  it("renders an SVG element", () => {
    const { container } = render(<IntentScoreGauge score={80} confidence={0.85} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("accepts custom size prop", () => {
    const { container } = render(<IntentScoreGauge score={50} confidence={0.5} size={200} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "200");
  });
});
