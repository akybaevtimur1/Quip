import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ImageResponse } from "next/og";
import { siteConfig } from "@/lib/site";

// Site-wide social card. Generated at build with a local TTF (no network fetch).
export const runtime = "nodejs";
export const alt = siteConfig.ogImageAlt;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  const font = readFileSync(join(process.cwd(), "public/libass/fonts/Montserrat.ttf"));

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#0a0b0f",
          color: "#edf0f8",
          padding: "72px",
          fontFamily: "Quip",
        }}
      >
        {/* logo */}
        <div style={{ display: "flex", alignItems: "center", gap: "18px" }}>
          <div
            style={{
              width: "56px",
              height: "56px",
              borderRadius: "14px",
              background: "#ff5a3d",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              style={{
                width: 0,
                height: 0,
                borderLeft: "22px solid #fff",
                borderTop: "14px solid transparent",
                borderBottom: "14px solid transparent",
                marginLeft: "6px",
              }}
            />
          </div>
          <div style={{ fontSize: "42px", fontWeight: 800, letterSpacing: "-0.02em" }}>Quip</div>
        </div>

        {/* headline */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            fontSize: "82px",
            fontWeight: 800,
            lineHeight: 1.04,
            letterSpacing: "-0.03em",
            maxWidth: "1010px",
          }}
        >
          <span>Don&rsquo;t just get clips.&nbsp;</span>
          <span style={{ color: "#ff5a3d" }}>Know why&nbsp;</span>
          <span>they&rsquo;re worth posting.</span>
        </div>

        {/* eyebrow */}
        <div style={{ display: "flex", alignItems: "center", gap: "14px", fontSize: "27px", color: "#7e8aa4" }}>
          <div style={{ width: "11px", height: "11px", borderRadius: "999px", background: "#ff5a3d" }} />
          Explainable AI clips — a hook, a confidence score, and the reason it works.
        </div>
      </div>
    ),
    { ...size, fonts: [{ name: "Quip", data: font, style: "normal", weight: 700 }] },
  );
}
