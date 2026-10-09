/**
 * The files picked in a file input, cleared so picking the same file again
 * fires `change` once more. Copied first: clearing empties the input's FileList.
 */
export function takeFiles(event) {
  const files = [...event.target.files]
  event.target.value = ''
  return files
}
