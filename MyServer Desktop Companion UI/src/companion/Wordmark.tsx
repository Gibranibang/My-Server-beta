import { assets } from "./assets"

/** "My-Server" lockup from the Figma logo: script "My", matrix "-Server", lime dot and "by algitha" signature. */
export default function Wordmark() {
  return (
    <div className="relative inline-flex items-baseline text-ink-soft select-none">
      <span className="font-script text-wordmark-script tracking-[-0.02em]">
        My
      </span>
      <span className="rond-0 font-matrix text-wordmark font-black tracking-[-0.02em]">
        -
      </span>
      <span className="relative rond-0 font-matrix text-wordmark font-black tracking-[-0.02em] text-brand">
        Server
        <img
          src={assets.logoDot}
          alt=""
          width={4}
          height={4}
          className="absolute top-0 -right-1.5 size-1"
        />
        <span className="absolute top-full right-0 mt-0.5 font-signature text-micro leading-none font-semibold whitespace-nowrap text-ink-muted italic">
          by algitha
        </span>
      </span>
    </div>
  )
}
