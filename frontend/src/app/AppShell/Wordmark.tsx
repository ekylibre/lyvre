/** Logotype « lyvre » : y en lichen, ou en paille sur fond sombre (charte, composant Logo). */
export function Wordmark({ onDark = false }: { onDark?: boolean }) {
  return (
    <span className="lv-wordmark" data-on-dark={onDark || undefined} aria-label="Lyvre">
      l<span>y</span>vre
    </span>
  );
}
