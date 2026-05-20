import { render, screen, fireEvent } from "@testing-library/react";
import { NBAActionCard } from "../NBAActionCard";
import type { NextBestAction } from "@/lib/types";

const makeAction = (overrides: Partial<NextBestAction> = {}): NextBestAction => ({
  id: "nba-test-1",
  account_domain: "acme.com",
  action_type: "NURTURE",
  priority: 7,
  rationale: "Default nurture sequence — no urgent signals detected.",
  fatigue_score: 32.0,
  intent_score: 55.0,
  churn_probability: 0.12,
  is_active: true,
  expires_at: null,
  created_at: "2024-07-01T10:00:00Z",
  ...overrides,
});

describe("NBAActionCard", () => {
  it("renders action label", () => {
    render(<NBAActionCard action={makeAction()} />);
    expect(screen.getByText("Nurture")).toBeInTheDocument();
  });

  it("renders rationale text", () => {
    const action = makeAction({ rationale: "This is the rationale." });
    render(<NBAActionCard action={action} />);
    expect(screen.getByText("This is the rationale.")).toBeInTheDocument();
  });

  it("renders priority watermark number", () => {
    render(<NBAActionCard action={makeAction({ priority: 3 })} />);
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it.each([
    ["COOLDOWN",        "Cooldown"],
    ["DEAL_REVIEW",     "Deal Review"],
    ["EXEC_ESCALATION", "Exec Escalation"],
    ["PRICING_TRIGGER", "Pricing Trigger"],
    ["ACCELERATE",      "Accelerate"],
    ["RE_ENGAGE",       "Re-engage"],
    ["NURTURE",         "Nurture"],
  ] as const)("renders correct label for action_type=%s", (action_type, label) => {
    render(<NBAActionCard action={makeAction({ action_type })} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("renders score indicators", () => {
    render(
      <NBAActionCard
        action={makeAction({ fatigue_score: 45, intent_score: 72, churn_probability: 0.18 })}
      />
    );
    expect(screen.getByText("45")).toBeInTheDocument(); // fatigue
    expect(screen.getByText("72")).toBeInTheDocument(); // intent
    expect(screen.getByText("18%")).toBeInTheDocument(); // churn
  });

  it("does not render dispatch button when onDispatch is not provided", () => {
    render(<NBAActionCard action={makeAction()} />);
    expect(screen.queryByText(/dispatch/i)).not.toBeInTheDocument();
  });

  it("renders dispatch button when onDispatch is provided", () => {
    render(<NBAActionCard action={makeAction()} onDispatch={vi.fn()} />);
    expect(screen.getByText(/dispatch action/i)).toBeInTheDocument();
  });

  it("calls onDispatch with the action when button is clicked", () => {
    const onDispatch = vi.fn();
    const action = makeAction({ action_type: "ACCELERATE" });
    render(<NBAActionCard action={action} onDispatch={onDispatch} />);
    fireEvent.click(screen.getByText(/dispatch action/i));
    expect(onDispatch).toHaveBeenCalledWith(action);
  });
});
