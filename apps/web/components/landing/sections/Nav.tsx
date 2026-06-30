"use client";

import { useState } from "react";
import { useScroll, useMotionValueEvent, AnimatePresence, motion, useReducedMotion } from "motion/react";
import { List, X } from "@phosphor-icons/react/dist/ssr";
import { useLocale } from "next-intl";
import { LocaleSwitcher } from "@/components/i18n/LocaleSwitcher";
import { resolveLocale } from "@/i18n/locale";
import { getLandingContent, ROUTES } from "@/lib/landingContent";
import { PrimaryCTA } from "../components/CTA";

export function Logo() {
  return (
    <a href="#top" className="flex items-center gap-2.5" aria-label="Quip home">
      {/* Brand mark (the Quip "Q"). Plain <img> for a tiny static logo, like ClipCard. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/icon.png" alt="Quip" width={28} height={28} className="size-7 object-contain" />
      <span className="text-[19px] font-extrabold tracking-[-0.02em] text-ink">Quip</span>
    </a>
  );
}

export function Nav({ authed = false }: { authed?: boolean }) {
  const { nav, openApp } = getLandingContent(resolveLocale(useLocale()));
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const { scrollY } = useScroll();
  const reduce = useReducedMotion();
  useMotionValueEvent(scrollY, "change", (y) => setScrolled(y > 12));

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-colors duration-300 ${
        scrolled || open ? "border-b border-line bg-bg/80 backdrop-blur-xl" : "border-b border-transparent"
      }`}
    >
      <nav className="container-page flex h-16 items-center justify-between gap-6">
        <Logo />

        <div className="hidden items-center gap-8 md:flex">
          {nav.items.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="text-[14px] text-muted transition-colors duration-150 hover:text-ink"
            >
              {item.label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <LocaleSwitcher className="hidden sm:inline-flex" />
          <a
            href={authed ? ROUTES.app : ROUTES.login}
            className="hidden text-[14px] text-muted transition-colors duration-150 hover:text-ink sm:inline"
          >
            {authed ? nav.dashboard : nav.signIn}
          </a>
          <PrimaryCTA href={authed ? ROUTES.app : ROUTES.signup} arrow={false} className="h-9 px-4 text-[14px]">
            {authed ? openApp : nav.tryFree}
          </PrimaryCTA>
          <button
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            className="grid size-9 place-items-center rounded-[8px] border border-line text-ink md:hidden"
          >
            {open ? <X weight="bold" className="size-4" /> : <List weight="bold" className="size-4" />}
          </button>
        </div>
      </nav>

      {/* mobile disclosure menu */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={reduce ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduce ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.2, 0.7, 0.2, 1] }}
            className="overflow-hidden md:hidden"
          >
            <div className="container-page flex flex-col gap-1 pb-4 pt-2">
              {nav.items.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className="py-2.5 text-[15px] text-muted transition-colors hover:text-ink"
                >
                  {item.label}
                </a>
              ))}
              <a
                href={authed ? ROUTES.app : ROUTES.login}
                onClick={() => setOpen(false)}
                className="border-t border-line py-2.5 pt-3.5 text-[15px] text-muted transition-colors hover:text-ink"
              >
                {authed ? nav.dashboard : nav.signIn}
              </a>
              <div className="flex items-center gap-3 border-t border-line pt-3.5">
                <span className="text-[15px] text-muted">Язык / Language</span>
                <LocaleSwitcher />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
