import { redirect } from "next/navigation";

export default function BrainPage() {
  // Legacy compatibility route: the landing page is now the primary Brain view.
  redirect("/");
}
