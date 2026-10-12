import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MessageItem } from "./chat";
import { LiveActivityBar } from "./chat";
import type { Message } from "../types";

const baseMessage: Message = { role: "assistant", content: "Hola **mundo**" };

afterEach(cleanup);

const handlers = {
  onDraftChange: vi.fn(),
  onSaveEdit: vi.fn(),
  onCancelEdit: vi.fn(),
  onCopy: vi.fn(),
  onEdit: vi.fn()
};

function renderMessage(message: Message, overrides: Partial<Parameters<typeof MessageItem>[0]> = {}) {
  return render(
    <MessageItem
      message={message}
      index={0}
      isEditing={false}
      editingDraft=""
      isCopied={false}
      {...handlers}
      {...overrides}
    />
  );
}

describe("MessageItem", () => {
  it("renders assistant content as markdown", () => {
    renderMessage(baseMessage);
    expect(screen.getByText("mundo").tagName).toBe("STRONG");
  });

  it("shows the edit button only for user messages", () => {
    const { rerender } = renderMessage(baseMessage);
    expect(screen.queryByTitle("Editar")).toBeNull();

    rerender(
      <MessageItem
        message={{ role: "user", content: "pregunta" }}
        index={0}
        isEditing={false}
        editingDraft=""
        isCopied={false}
        {...handlers}
      />
    );
    expect(screen.getByTitle("Editar")).toBeTruthy();
  });

  it("switches to an editor in editing mode and saves with the index", () => {
    renderMessage(baseMessage, { isEditing: true, editingDraft: "nuevo texto" });
    const area = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(area.value).toBe("nuevo texto");

    fireEvent.click(screen.getByText("Guardar"));
    expect(handlers.onSaveEdit).toHaveBeenCalledWith(0);

    fireEvent.click(screen.getByText("Cancelar"));
    expect(handlers.onCancelEdit).toHaveBeenCalledTimes(1);
  });

  it("triggers copy with the index", () => {
    renderMessage(baseMessage);
    fireEvent.click(screen.getByTitle("Copiar"));
    expect(handlers.onCopy).toHaveBeenCalledWith(0);
  });
});

describe("LiveActivityBar", () => {
  it("renders elapsed time and label", () => {
    const now = Date.now();
    render(<LiveActivityBar activity={{ label: "ejecutando tool", startedAt: now - 65000, lastAt: now }} />);
    expect(screen.getByText(/⏱ 01:05/)).toBeTruthy();
    expect(screen.getByText("ejecutando tool")).toBeTruthy();
  });

  it("marks stale activity after 45s without signal", () => {
    const now = Date.now();
    render(<LiveActivityBar activity={{ label: "x", startedAt: now - 100000, lastAt: now - 50000 }} />);
    expect(screen.getByText(/sin señal nueva hace/)).toBeTruthy();
  });
});
