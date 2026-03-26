import { redirect } from "next/navigation";

export default function GgufPage() {
  redirect("/settings?tab=models");
}
