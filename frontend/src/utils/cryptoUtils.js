import forge from 'node-forge';

/**
 * Computes the SHA-256 hash of a file's contents.
 * @param {File|ArrayBuffer} file 
 * @returns {Promise<string>} Hex representation of the SHA-256 hash
 */
export async function computeFileHash(fileOrBuffer) {
  return new Promise((resolve, reject) => {
    if (fileOrBuffer instanceof File || fileOrBuffer instanceof Blob) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const buffer = e.target.result;
        const md = forge.md.sha256.create();
        md.update(forge.util.createBuffer(buffer).getBytes());
        resolve(md.digest().toHex());
      };
      reader.onerror = reject;
      reader.readAsArrayBuffer(fileOrBuffer);
    } else {
      const md = forge.md.sha256.create();
      md.update(forge.util.createBuffer(fileOrBuffer).getBytes());
      resolve(md.digest().toHex());
    }
  });
}

