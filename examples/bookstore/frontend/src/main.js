/** Optional catalog filter widget. The page is already usable without JS. */

const input = document.querySelector("[data-live-search]");
if (input) {
  let timer = 0;
  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(async () => {
      const q = input.value.trim();
      const res = await fetch("/api/books?q=" + encodeURIComponent(q));
      if (!res.ok) return;
      const books = await res.json();
      const root = document.querySelector("[data-catalog]");
      if (!root) return;
      if (!books.length) {
        root.innerHTML =
          '<div class="empty"><p>Nothing on the shelves matches that.</p></div>';
        return;
      }
      root.innerHTML = books
        .map(
          (b) =>
            `<a class="card" href="/books/${b.id}"><h2>${escapeHtml(
              b.title,
            )}</h2><p class="by">${escapeHtml(b.author)}</p><p class="price">$${Number(
              b.price,
            ).toFixed(2)}</p></a>`,
        )
        .join("");
    }, 180);
  });
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
