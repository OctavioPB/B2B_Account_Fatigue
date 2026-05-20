import { redirect } from "next/navigation";

// Root path redirects to the main dashboard view.
export default function RootPage() {
  redirect("/dashboard");
}
