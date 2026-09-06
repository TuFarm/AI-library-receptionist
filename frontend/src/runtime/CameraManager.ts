import { hasLiveVideoTrack, waitForVideoFrame } from "../config/cameraRuntime";

async function attach(video: HTMLVideoElement, stream: MediaStream) {
  if (video.srcObject !== stream) video.srcObject = stream;
  video.muted = true; video.playsInline = true;
  try { await video.play(); } catch { /* capture readiness reports errors */ }
}

export class CameraManager {
  private stream: MediaStream | null = null;
  private captureVideo: HTMLVideoElement | null = null;
  private preview: HTMLVideoElement | null = null;
  private generation = 0;
  get live() { return hasLiveVideoTrack(this.stream); }
  private captureElement() {
    if (!this.captureVideo) {
      this.captureVideo = document.createElement("video");
      this.captureVideo.autoplay = true; this.captureVideo.muted = true; this.captureVideo.playsInline = true;
    }
    return this.captureVideo;
  }
  async start() {
    if (this.live) {
      await attach(this.captureElement(), this.stream!);
      if (this.preview) await attach(this.preview, this.stream!);
      return true;
    }
    const generation = this.generation;
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1920, min: 1280 }, height: { ideal: 1080, min: 720 }, frameRate: { ideal: 30, max: 30 } },
      audio: false,
    });
    if (generation !== this.generation) { stream.getTracks().forEach(track => track.stop()); return false; }
    this.stream?.getTracks().forEach(track => track.stop());
    this.stream = stream;
    await attach(this.captureElement(), stream);
    if (this.preview) await attach(this.preview, stream);
    return true;
  }
  setPreview(video: HTMLVideoElement | null) {
    this.preview = video;
    if (video && this.live) void attach(video, this.stream!);
  }
  async captureNativeFrame() {
    if (!this.live) throw new Error("Camera đã ngắt kết nối.");
    const video = this.captureElement();
    await attach(video, this.stream!);
    if (!await waitForVideoFrame(video)) throw new Error("Camera đang khởi động.");
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Không thể đọc khung hình camera.");
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    return new Promise<Blob>((resolve, reject) => canvas.toBlob(
      blob => blob ? resolve(blob) : reject(new Error("Không thể mã hóa khung hình camera.")), "image/jpeg", .78,
    ));
  }
  stop() {
    this.generation += 1;
    this.stream?.getTracks().forEach(track => track.stop());
    this.stream = null;
    if (this.preview) this.preview.srcObject = null;
    if (this.captureVideo) this.captureVideo.srcObject = null;
  }
}
