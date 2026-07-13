// Converts ```mermaid fenced code blocks into <pre class="mermaid"> elements
// BEFORE Expressive Code touches them, so the raw diagram source reaches the
// client untouched. Mermaid then renders them in the browser (see Head.astro).

function escapeHtml(value) {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export default function remarkMermaid() {
  return (tree) => walk(tree);
}

function walk(node) {
  if (!node || !Array.isArray(node.children)) return;
  for (let i = 0; i < node.children.length; i++) {
    const child = node.children[i];
    if (child.type === 'code' && child.lang === 'mermaid') {
      node.children[i] = {
        type: 'html',
        value: `<pre class="mermaid" role="img" aria-label="diagram">${escapeHtml(child.value)}</pre>`,
      };
    } else {
      walk(child);
    }
  }
}
