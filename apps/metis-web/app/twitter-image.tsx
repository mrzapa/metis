// Twitter card uses the same image as Open Graph. We re-export the
// rendering handler + metadata fields, but route segment config
// (runtime/dynamic) cannot be re-exported — Next.js statically
// parses those — so we declare them inline here.
export const dynamic = "force-static";
export { default, alt, size, contentType } from "./opengraph-image";
