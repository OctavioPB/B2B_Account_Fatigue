import { render, screen } from "@testing-library/react";
import { FatigueScoreBadge } from "../FatigueScoreBadge";

describe("FatigueScoreBadge", () => {
  it("renders the severity label", () => {
    render(<FatigueScoreBadge score={85} severity="CRITICAL" />);
    expect(screen.getByText(/critical/i)).toBeInTheDocument();
  });

  it("renders the score when showScore=true (default)", () => {
    render(<FatigueScoreBadge score={72} severity="HIGH" />);
    expect(screen.getByText("72")).toBeInTheDocument();
  });

  it("does not render score when showScore=false", () => {
    render(<FatigueScoreBadge score={72} severity="HIGH" showScore={false} />);
    expect(screen.queryByText("72")).not.toBeInTheDocument();
  });

  it.each([
    ["CRITICAL", "Critical"],
    ["HIGH",     "High"],
    ["MEDIUM",   "Medium"],
    ["LOW",      "Low"],
  ] as const)("renders correct label for severity=%s", (severity, label) => {
    render(<FatigueScoreBadge score={50} severity={severity} />);
    expect(screen.getByText(new RegExp(label, "i"))).toBeInTheDocument();
  });

  it("rounds float scores", () => {
    render(<FatigueScoreBadge score={42.7} severity="MEDIUM" />);
    expect(screen.getByText("43")).toBeInTheDocument();
  });

  it("has accessible role via inline element", () => {
    const { container } = render(<FatigueScoreBadge score={30} severity="LOW" />);
    // Badge is a <span> — confirm it renders into the DOM
    expect(container.querySelector("span")).toBeInTheDocument();
  });
});
