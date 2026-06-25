"use client";

import { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { Plus } from "@phosphor-icons/react/dist/ssr";
import { FAQ } from "@/lib/landingContent";
import { Container, Section } from "../components/primitives";
import { Reveal } from "../components/Reveal";

export function Faq() {
  const [open, setOpen] = useState<number | null>(0);
  const reduce = useReducedMotion();

  return (
    <Section id="faq">
      <Container>
        <div className="grid gap-12 lg:grid-cols-[minmax(0,32fr)_minmax(0,68fr)]">
          <Reveal>
            <h2 className="text-[clamp(28px,3.6vw,44px)] font-bold leading-[1.08] tracking-[-0.025em] text-ink">
              {FAQ.heading}
            </h2>
          </Reveal>

          <Reveal delay={0.05}>
            <div className="border-t border-line">
              {FAQ.items.map((item, i) => {
                const isOpen = open === i;
                return (
                  <div key={item.q} className="border-b border-line">
                    <button
                      onClick={() => setOpen(isOpen ? null : i)}
                      aria-expanded={isOpen}
                      className="flex w-full items-center justify-between gap-6 py-5 text-left"
                    >
                      <span className="text-[1.0625rem] font-medium tracking-[-0.01em] text-ink">{item.q}</span>
                      <Plus
                        weight="bold"
                        className={`size-4 shrink-0 text-muted transition-transform duration-300 ease-[var(--ease-snappy)] ${
                          isOpen ? "rotate-45" : ""
                        }`}
                      />
                    </button>
                    <AnimatePresence initial={false}>
                      {isOpen && (
                        <motion.div
                          initial={reduce ? false : { height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={reduce ? undefined : { height: 0, opacity: 0 }}
                          transition={{ duration: 0.3, ease: [0.2, 0.7, 0.2, 1] }}
                          className="overflow-hidden"
                        >
                          <p className="max-w-[64ch] pb-6 pr-10 text-[15px] leading-relaxed text-muted">{item.a}</p>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                );
              })}
            </div>
          </Reveal>
        </div>
      </Container>
    </Section>
  );
}
