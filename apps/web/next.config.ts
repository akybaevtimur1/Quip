import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const nextConfig: NextConfig = {
  /* config options here */
};

// next-intl cookie mode: wires i18n/request.ts (reads the NEXT_LOCALE cookie) into the
// build so getTranslations / useTranslations / getLocale resolve per request.
const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

export default withNextIntl(nextConfig);
