/**
 * Regression tests for the mobile microphone bug.
 *
 * Root cause: both VoiceMicButton and useVoiceTranscript hardcode
 * `{ type: "audio/webm" }` when constructing the final Blob.  On iOS
 * Safari, MediaRecorder produces native mp4/aac — the webm label
 * causes the Groq backend to reject or mis-parse the file, silently
 * dropping the transcription.  The fix: negotiate the MIME type at
 * MediaRecorder construction time (preferring audio/mp4 when webm is
 * unsupported) and use that same type on the Blob.
 *
 * Goodhart canary:
 *  - Canary A: getUserMedia called with audio:true constraint
 *  - Canary B: MediaRecorder instantiated with the negotiated mimeType (not hardcoded webm)
 *  - Canary C: Blob constructed with the recorder's actual mimeType (the original bug)
 *  - Canary D: getUserMedia rejection → error state set, button returns to idle
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { VoiceMicButton } from "./VoiceMicButton";

// ---------------------------------------------------------------------------
// Hoisted mock — vi.mock is hoisted before imports so must live at top level
// ---------------------------------------------------------------------------
vi.mock("@/lib/api", () => ({
  api: {
    transcribeAudio: vi.fn().mockResolvedValue({ transcript: "hello" }),
  },
}));

// ---------------------------------------------------------------------------
// Helpers — minimal MediaRecorder/MediaDevices stubs
// ---------------------------------------------------------------------------

interface FakeRecorder {
  mimeType: string;
  state: string;
  start: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
  ondataavailable: ((e: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
  _triggerStop: () => void;
}

// Shared state — reset in beforeEach
let capturedRecorderMimeType: string | undefined;
let capturedBlobType: string | undefined;
// Box so Canary C can read the recorder after it is assigned inside the constructor mock
const recorderBox: { current: FakeRecorder | null } = { current: null };

function installMocks(options: {
  getUserMediaRejects?: boolean;
  preferredMime?: string;
}) {
  const { getUserMediaRejects = false, preferredMime = "audio/mp4" } = options;

  const fakeStream = { getTracks: () => [{ stop: vi.fn() }] };

  vi.stubGlobal("navigator", {
    mediaDevices: {
      getUserMedia: getUserMediaRejects
        ? vi.fn().mockRejectedValue(new DOMException("NotAllowedError", "NotAllowedError"))
        : vi.fn().mockResolvedValue(fakeStream),
    },
  });

  // Must be a regular function (not arrow) so `new` works in jsdom.
  // We assign the fake recorder props onto `this` AND store `this` in recorderBox
  // so _triggerStop (called in tests) reads the same ondataavailable/onstop
  // that the component set on the instance after construction.
  function MockMediaRecorder(this: FakeRecorder, _stream: unknown, opts?: { mimeType?: string }) {
    capturedRecorderMimeType = opts?.mimeType;
    const mime = opts?.mimeType ?? "";
    this.mimeType = mime;
    this.state = "inactive";
    this.start = vi.fn(() => { this.state = "recording"; });
    this.stop = vi.fn(() => { this.state = "inactive"; });
    this.ondataavailable = null;
    this.onstop = null;
    this._triggerStop = () => {
      if (this.ondataavailable) this.ondataavailable({ data: new Blob(["audio"], { type: mime }) });
      if (this.onstop) this.onstop();
    };
    recorderBox.current = this;
  }
  (MockMediaRecorder as unknown as { isTypeSupported: (t: string) => boolean }).isTypeSupported =
    vi.fn((type: string) => type === preferredMime);

  vi.stubGlobal("MediaRecorder", MockMediaRecorder);

  // Capture the Blob type by inspecting the argument passed to api.transcribeAudio.
  // Spying on the Blob constructor directly produces a non-constructable arrow function,
  // breaking _triggerStop's `new Blob(...)` call inside the mock.
  const { api } = await import("@/lib/api");
  vi.mocked(api.transcribeAudio).mockImplementation(async (blob: Blob) => {
    capturedBlobType = blob.type;
    return { transcript: "hello" };
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  capturedRecorderMimeType = undefined;
  capturedBlobType = undefined;
  recorderBox.current = null;
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("VoiceMicButton — mobile MIME type negotiation", () => {
  it("Canary A: calls getUserMedia with { audio: true }", async () => {
    installMocks({ preferredMime: "audio/mp4" });
    render(<VoiceMicButton onTranscript={vi.fn()} ariaLabel="Dictate" />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });

    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ audio: true });
  });

  it("Canary B (FAILS before fix): MediaRecorder receives negotiated mimeType, not hardcoded webm", async () => {
    installMocks({ preferredMime: "audio/mp4" });
    render(<VoiceMicButton onTranscript={vi.fn()} ariaLabel="Dictate" />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });

    // Before fix: capturedRecorderMimeType is undefined (no mimeType passed)
    // After fix:  capturedRecorderMimeType === "audio/mp4"
    expect(capturedRecorderMimeType).toBe("audio/mp4");
  });

  it("Canary C (FAILS before fix): Blob type matches recorder mimeType, not hardcoded webm", async () => {
    installMocks({ preferredMime: "audio/mp4" });
    const onTranscript = vi.fn();
    render(<VoiceMicButton onTranscript={onTranscript} ariaLabel="Dictate" />);

    // Start recording
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });

    // Stop recording + trigger onstop so the Blob is built
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });

    await act(async () => {
      recorderBox.current?._triggerStop();
    });

    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith("hello"));

    // Before fix: capturedBlobType === "audio/webm"
    // After fix:  capturedBlobType === "audio/mp4"
    expect(capturedBlobType).toBe("audio/mp4");
  });

  it("Canary D: getUserMedia rejection → error shown, button returns to idle", async () => {
    installMocks({ getUserMediaRejects: true });
    render(<VoiceMicButton onTranscript={vi.fn()} ariaLabel="Dictate" />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });

    const btn = screen.getByRole("button");
    expect(btn.textContent).toContain("Mic");
    expect(btn.getAttribute("title")).toMatch(/NotAllowedError/);
  });
});
