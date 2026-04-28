// Twitter card uses the same image as Open Graph. Re-exporting the
// Next.js metadata-route handler keeps the two surfaces in sync.
export {
  default,
  alt,
  size,
  contentType,
  runtime,
} from "./opengraph-image";
