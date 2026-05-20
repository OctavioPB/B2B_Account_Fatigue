import { render, screen } from "@testing-library/react";
import { CommitteeHeatmap } from "../CommitteeHeatmap";

const MOCK_DATA = [
  { memberName: "Sarah Chen",  memberTitle: "CFO", email: 10, web: 3, webinar: 2, crm: 1 },
  { memberName: "Marcus Webb", memberTitle: "CTO", email: 2,  web: 8, webinar: 0, crm: 0 },
];

describe("CommitteeHeatmap", () => {
  it("renders member names", () => {
    render(<CommitteeHeatmap data={MOCK_DATA} />);
    expect(screen.getByText("Sarah Chen")).toBeInTheDocument();
    expect(screen.getByText("Marcus Webb")).toBeInTheDocument();
  });

  it("renders member titles", () => {
    render(<CommitteeHeatmap data={MOCK_DATA} />);
    expect(screen.getByText("CFO")).toBeInTheDocument();
    expect(screen.getByText("CTO")).toBeInTheDocument();
  });

  it("renders all four channel headers", () => {
    render(<CommitteeHeatmap data={MOCK_DATA} />);
    for (const ch of ["email", "web", "webinar", "crm"]) {
      expect(screen.getAllByText(new RegExp(ch, "i")).length).toBeGreaterThan(0);
    }
  });

  it("renders em-dash for zero cells", () => {
    render(<CommitteeHeatmap data={MOCK_DATA} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("renders empty state when no data", () => {
    render(<CommitteeHeatmap data={[]} />);
    expect(screen.getByText(/no committee member data/i)).toBeInTheDocument();
  });

  it("renders as an accessible table", () => {
    render(<CommitteeHeatmap data={MOCK_DATA} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});
