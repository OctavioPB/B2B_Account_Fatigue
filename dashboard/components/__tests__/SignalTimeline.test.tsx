import { render, screen } from "@testing-library/react";
import { SignalTimeline, type TimelineSignal } from "../SignalTimeline";

const makeSignal = (overrides: Partial<TimelineSignal> = {}): TimelineSignal => ({
  id: "s1",
  signal_type: "email_open",
  channel: "email",
  member_name: "Alice Smith",
  occurred_at: new Date(Date.now() - 3600000).toISOString(),
  ...overrides,
});

describe("SignalTimeline", () => {
  it("renders a signal entry", () => {
    render(<SignalTimeline signals={[makeSignal()]} />);
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
  });

  it("renders signal type as formatted label", () => {
    render(<SignalTimeline signals={[makeSignal({ signal_type: "pricing_page_view" })]} />);
    expect(screen.getByText("Pricing Page View")).toBeInTheDocument();
  });

  it("renders channel badge", () => {
    render(<SignalTimeline signals={[makeSignal({ channel: "web" })]} />);
    expect(screen.getByText("web")).toBeInTheDocument();
  });

  it("renders empty state when no signals", () => {
    render(<SignalTimeline signals={[]} />);
    expect(screen.getByText(/no signals/i)).toBeInTheDocument();
  });

  it("respects maxItems limit", () => {
    const signals = Array.from({ length: 8 }, (_, i) =>
      makeSignal({ id: `s${i}`, member_name: `Member ${i}` })
    );
    render(<SignalTimeline signals={signals} maxItems={3} />);
    expect(screen.getAllByText(/member \d/i)).toHaveLength(3);
  });

  it("falls back gracefully for unknown member", () => {
    render(
      <SignalTimeline signals={[makeSignal({ member_name: undefined })]} />
    );
    expect(screen.getByText(/unknown member/i)).toBeInTheDocument();
  });
});
