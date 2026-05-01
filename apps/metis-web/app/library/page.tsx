// M21 #2 — restore the NYX component catalog at /library/.
//
// The previous stub was `notFound()`, but every chat artifact card
// deep-links to /library/<component> and tests assert the href; the
// catalog component itself
// (apps/metis-web/components/library/nyx-catalog-page.tsx) was always
// fully implemented. Wiring the existing component to the route is the
// minimal fix. The /library/[component]/ detail route stays out of
// scope for this phase — that's a separate addition.
import { NyxCatalogPage } from "@/components/library/nyx-catalog-page";

export default function LibraryPage() {
  return <NyxCatalogPage />;
}
