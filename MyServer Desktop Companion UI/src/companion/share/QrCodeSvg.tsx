import { useMemo } from "react"
import { encode } from "uqr"

export interface QrCodeSvgProps {
  url: string
  ariaLabel: string
  fallbackText?: string
}

export function QrCodeSvg({ url, ariaLabel, fallbackText }: QrCodeSvgProps) {
  const encoded = useMemo(() => {
    const trimmed = typeof url === "string" ? url.trim() : ""
    if (!trimmed) return null
    try {
      const qr = encode(trimmed, { ecc: "M", border: 0 })
      if (!qr || !qr.size || !Array.isArray(qr.data)) return null
      const segments: string[] = []
      for (let y = 0; y < qr.size; y++) {
        const row = qr.data[y]
        if (!row) continue
        for (let x = 0; x < qr.size; x++) {
          if (row[x]) {
            segments.push(`M${x} ${y}h1v1h-1z`)
          }
        }
      }
      if (segments.length === 0) return null
      return { size: qr.size, d: segments.join("") }
    } catch {
      return null
    }
  }, [url])

  if (!encoded) {
    return (
      <div
        data-testid="qr-fallback"
        className="flex size-32 shrink-0 items-center justify-center rounded-control border border-[var(--line)] bg-[var(--surface-elevated)] p-2 text-center text-caption font-normal text-[var(--ink-subtle)]"
      >
        {fallbackText || "QR preview unavailable"}
      </div>
    )
  }

  return (
    <div className="flex size-32 shrink-0 items-center justify-center rounded-control bg-[#FFFFFF] p-2">
      <svg
        role="img"
        aria-label={ariaLabel}
        width={112}
        height={112}
        viewBox={`0 0 ${encoded.size} ${encoded.size}`}
        shapeRendering="crispEdges"
      >
        <rect width={encoded.size} height={encoded.size} fill="#FFFFFF" />
        <path d={encoded.d} fill="#000000" />
      </svg>
    </div>
  )
}

export default QrCodeSvg
