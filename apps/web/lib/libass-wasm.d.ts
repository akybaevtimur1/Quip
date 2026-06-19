declare module "libass-wasm" {
  export interface SubtitlesOctopusOptions {
    video?: HTMLVideoElement;
    canvas?: HTMLCanvasElement;
    subContent?: string;
    workerUrl?: string;
    legacyWorkerUrl?: string;
    fonts?: string[];
    fallbackFont?: string;
    timeOffset?: number;
    onReady?: () => void;
    onError?: (error: unknown) => void;
    debug?: boolean;
    [key: string]: unknown;
  }
  /** One blit rect posted by the worker per frame in wasm-blend mode (device px). */
  export interface OctopusCanvasRect {
    x: number;
    y: number;
    w: number;
    h: number;
    buffer: ArrayBuffer;
  }
  /** `op:"renderCanvas"` payload from the worker (default wasm-blend mode). */
  export interface OctopusRenderCanvasMessage {
    target: "canvas";
    op: "renderCanvas";
    time: number;
    canvases: OctopusCanvasRect[];
  }
  export default class SubtitlesOctopus {
    constructor(options: SubtitlesOctopusOptions);
    /** Underlying Web Worker (public on the instance) — we tap its messages for the rect. */
    worker?: Worker;
    /** Live canvas the instance draws into (its pixel size is the device-px grid). */
    canvas?: HTMLCanvasElement;
    setTrack(content: string): void;
    setCurrentTime(seconds: number): void;
    resize(width?: number, height?: number, top?: number, left?: number): void;
    freeTrack(): void;
    dispose(): void;
  }
}
