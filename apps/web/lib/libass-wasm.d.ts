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
  export default class SubtitlesOctopus {
    constructor(options: SubtitlesOctopusOptions);
    setTrack(content: string): void;
    setCurrentTime(seconds: number): void;
    resize(width?: number, height?: number, top?: number, left?: number): void;
    freeTrack(): void;
    dispose(): void;
  }
}
