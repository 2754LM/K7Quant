import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const proFile = join(here, '../node_modules/@klinecharts/pro/dist/klinecharts-pro.js')
const viteProFile = join(here, '../node_modules/.vite/deps/@klinecharts_pro.js')

const marker = 'createIndicator: (...h) => n == null ? null : n.createIndicator(...h)'
const unpatched = `    setPeriod: M,
    getPeriod: () => L()
  });`

const overlayOnlyPatched = `    setPeriod: M,
    getPeriod: () => L(),
    createOverlay: (...h) => n == null ? null : n.createOverlay(...h),
    removeOverlay: (...h) => n == null ? void 0 : n.removeOverlay(...h),
    overrideOverlay: (...h) => n == null ? void 0 : n.overrideOverlay(...h)
  });`

const fullyPatched = `    setPeriod: M,
    getPeriod: () => L(),
    getDataList: (...h) => n == null ? [] : n.getDataList(...h),
    createOverlay: (...h) => n == null ? null : n.createOverlay(...h),
    removeOverlay: (...h) => n == null ? void 0 : n.removeOverlay(...h),
    overrideOverlay: (...h) => n == null ? void 0 : n.overrideOverlay(...h),
    createIndicator: (...h) => n == null ? null : n.createIndicator(...h),
    removeIndicator: (...h) => n == null ? void 0 : n.removeIndicator(...h),
    overrideIndicator: (...h) => n == null ? void 0 : n.overrideIndicator(...h),
    getIndicatorByPaneId: (...h) => n == null ? null : n.getIndicatorByPaneId(...h)
  });`

const dataAndOverlayPatched = `    setPeriod: M,
    getPeriod: () => L(),
    getDataList: (...h) => n == null ? [] : n.getDataList(...h),
    createOverlay: (...h) => n == null ? null : n.createOverlay(...h),
    removeOverlay: (...h) => n == null ? void 0 : n.removeOverlay(...h),
    overrideOverlay: (...h) => n == null ? void 0 : n.overrideOverlay(...h)
  });`

function patchFile(file, label, optional = false) {
  if (!existsSync(file)) {
    if (!optional) throw new Error(`[patch-klinecharts-pro] ${label} file not found`)
    return 'missing'
  }

  const source = readFileSync(file, 'utf8')
  if (source.includes(marker)) return 'already'

  const target = source.includes(dataAndOverlayPatched)
    ? dataAndOverlayPatched
    : source.includes(overlayOnlyPatched)
      ? overlayOnlyPatched
      : unpatched

  if (!source.includes(target)) {
    if (optional) return 'unmatched'
    throw new Error(`[patch-klinecharts-pro] target snippet not found in ${label}`)
  }

  writeFileSync(file, source.replace(target, fullyPatched))
  return 'patched'
}

const results = [
  ['@klinecharts/pro', patchFile(proFile, '@klinecharts/pro')],
  ['vite cache', patchFile(viteProFile, 'vite cache', true)],
]

const summary = results
  .filter(([, status]) => status !== 'missing')
  .map(([label, status]) => `${label}:${status}`)
  .join(', ')

console.log(`[patch-klinecharts-pro] ${summary || 'nothing to patch'}`)
