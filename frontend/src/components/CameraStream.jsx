import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { API_BASE_URL, formatISTDateTime } from "../config";

const JPEG_BOUNDARY = new TextEncoder().encode("--frame");
const HEADER_SEPARATOR = new TextEncoder().encode("\r\n\r\n");

function appendBytes(left, right) {
  const result = new Uint8Array(left.length + right.length);
  result.set(left);
  result.set(right, left.length);
  return result;
}

function findBytes(haystack, needle, start = 0) {
  outer: for (let index = start; index <= haystack.length - needle.length; index += 1) {
    for (let offset = 0; offset < needle.length; offset += 1) {
      if (haystack[index + offset] !== needle[offset]) continue outer;
    }
    return index;
  }
  return -1;
}

function parseContentLength(headerBytes) {
  const headers = new TextDecoder().decode(headerBytes);
  const match = headers.match(/content-length:\s*(\d+)/i);
  return match ? Number(match[1]) : 0;
}

function parseFrameTimestamp(headerBytes) {
  const headers = new TextDecoder().decode(headerBytes);
  const match = headers.match(/x-frame-received-at:\s*([^\r\n]+)/i);
  return match?.[1]?.trim() || new Date().toISOString();
}

function CameraStream({ roomId, cameraId, cameraStatus, retryNonce = 0 }) {
  const [streamState, setStreamState] = useState("IDLE");
  const [imageUrl, setImageUrl] = useState("");
  const [lastFrameAt, setLastFrameAt] = useState(null);
  const [error, setError] = useState("");
  const imageUrlRef = useRef("");
  const readerRef = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    const token = localStorage.getItem("hospital_admin_token");
    const streamUrl = `${API_BASE_URL}/api/monitoring/rooms/${encodeURIComponent(roomId)}/cameras/${encodeURIComponent(cameraId)}/stream`;

    const stopCurrentImage = () => {
      if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
      imageUrlRef.current = "";
      setImageUrl("");
    };

    const run = async () => {
      if (!cameraId) {
        stopCurrentImage();
        setStreamState("NO_CAMERA");
        return;
      }
      if (cameraStatus !== "CONNECTED") {
        stopCurrentImage();
        setStreamState(cameraStatus || "DISCONNECTED");
        return;
      }
      if (!token) {
        stopCurrentImage();
        setStreamState("AUTH_REQUIRED");
        return;
      }

      setStreamState("CONNECTING");
      setError("");
      try {
        const response = await fetch(streamUrl, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (response.status === 401 || response.status === 403) {
          throw new Error("Administrator authorization is required for camera preview.");
        }
        if (!response.ok || !response.body) {
          throw new Error("The camera preview could not be opened.");
        }

        const reader = response.body.getReader();
        readerRef.current = reader;
        let buffer = new Uint8Array();
        while (!controller.signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer = appendBytes(buffer, value);

          while (true) {
            const boundaryIndex = findBytes(buffer, JPEG_BOUNDARY);
            if (boundaryIndex < 0) break;
            buffer = buffer.slice(boundaryIndex + JPEG_BOUNDARY.length);
            if (buffer[0] === 13 && buffer[1] === 10) buffer = buffer.slice(2);
            const headerEnd = findBytes(buffer, HEADER_SEPARATOR);
            if (headerEnd < 0) break;
            const bodyStart = headerEnd + HEADER_SEPARATOR.length;
            const headerBytes = buffer.slice(0, headerEnd);
            const contentLength = parseContentLength(headerBytes);
            if (!contentLength || buffer.length < bodyStart + contentLength) break;
            const jpeg = buffer.slice(bodyStart, bodyStart + contentLength);
            buffer = buffer.slice(bodyStart + contentLength);
            const nextUrl = URL.createObjectURL(new Blob([jpeg], { type: "image/jpeg" }));
            if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
            imageUrlRef.current = nextUrl;
            setImageUrl(nextUrl);
            setLastFrameAt(parseFrameTimestamp(headerBytes));
            setStreamState("CONNECTED");
          }
        }
        if (!controller.signal.aborted) setStreamState("DISCONNECTED");
      } catch (streamError) {
        if (!controller.signal.aborted) {
          setError(streamError.message || "Camera preview failed.");
          setStreamState(streamError.message?.includes("authorization") ? "AUTH_REQUIRED" : "ERROR");
        }
      }
    };

    void run();
    return () => {
      controller.abort();
      readerRef.current?.cancel().catch(() => undefined);
      readerRef.current = null;
      stopCurrentImage();
    };
  }, [cameraId, cameraStatus, retryNonce, roomId]);

  if (streamState === "AUTH_REQUIRED") {
    return <div className="camera-state"><strong>Administrator authorization required</strong><p>Sign in through the Administration page to view camera previews.</p><Link className="camera-state-link" to="/admin">Open Administration</Link></div>;
  }
  if (streamState === "NO_CAMERA") {
    return <div className="camera-state"><strong>No camera assigned</strong><p>Configure an active camera for this room from Administration.</p></div>;
  }
  if (cameraStatus !== "CONNECTED") {
    return <div className="camera-state"><strong>Preview {cameraStatus || "unavailable"}</strong><p>The camera is not currently supplying fresh frames.</p><span>Last frame: {formatISTDateTime(lastFrameAt)}</span></div>;
  }
  return <div className="camera-stream-content">{imageUrl ? <img src={imageUrl} alt="Live camera preview" onError={() => setStreamState("ERROR")} /> : <div className="camera-state"><strong>{streamState === "ERROR" ? "Preview unavailable" : "Connecting to camera preview..."}</strong><p>{error || "Waiting for the next frame from the existing camera worker."}</p></div>}<div className="camera-stream-footer"><span>{streamState}</span><span>{lastFrameAt ? `Frame ${formatISTDateTime(lastFrameAt)}` : "Waiting for frame"}</span></div></div>;
}

export default CameraStream;
