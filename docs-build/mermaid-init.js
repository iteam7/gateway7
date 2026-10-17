/* Mermaid is bundled locally from the exact version in package-lock.json. */
document.addEventListener("DOMContentLoaded", async () => {
  const diagrams = [...document.querySelectorAll("pre > code.language-mermaid")].map((code) => {
    const diagram = document.createElement("div");
    diagram.className = "mermaid";
    diagram.textContent = code.textContent;
    code.parentElement.replaceWith(diagram);
    return diagram;
  });
  if (!diagrams.length) return;
  mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
  try {
    await mermaid.run({ nodes: diagrams });
    document.documentElement.dataset.mermaid = "ready";
  } catch (error) {
    document.documentElement.dataset.mermaid = "error";
    console.error("Documentation diagram rendering failed", error);
  }
});
