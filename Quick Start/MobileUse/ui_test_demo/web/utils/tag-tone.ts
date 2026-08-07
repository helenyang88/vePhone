export function tagToneClass(tag: string): string {
  let hash = 7;
  for (const char of tag) {
    hash = (hash * 33 + char.charCodeAt(0)) >>> 0;
  }
  return `tag-tone-${hash % 5}`;
}
