import type { MetadataRoute } from "next";

// Private dashboard: ask every crawler to stay out (pages also send noindex headers).
export default function robots(): MetadataRoute.Robots {
  return { rules: [{ userAgent: "*", disallow: "/" }] };
}
