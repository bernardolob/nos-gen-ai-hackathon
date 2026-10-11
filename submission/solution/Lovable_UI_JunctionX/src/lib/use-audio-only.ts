import { useEffect, useState } from "react";

import { isVideoFile } from "@/lib/review/api";

/**
 * Phones and WhatsApp save voice recordings as `.mp4` or `.mov`, so the file
 * looks like a video. This reads the file's metadata in the browser and says
 * whether it has no picture at all, so the screen can show the audio notice
 * (the sound goes to ElevenLabs) instead of the video one (frames go to
 * Gemini). The backend makes the same call when it receives the file.
 */
export function useAudioOnly(file: File | null): boolean {
  const [audioOnly, setAudioOnly] = useState(false);

  useEffect(() => {
    setAudioOnly(false);
    if (!file || !isVideoFile(file) || typeof URL.createObjectURL !== "function") return;
    let live = true;
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.muted = true;
    video.onloadedmetadata = () => {
      if (live) setAudioOnly(video.videoWidth === 0 && video.videoHeight === 0);
    };
    video.src = url;
    return () => {
      live = false;
      video.onloadedmetadata = null;
      video.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
  }, [file]);

  return audioOnly;
}
