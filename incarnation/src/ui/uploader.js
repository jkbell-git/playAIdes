/**
 * Uploads a File object to the specified URL via POST multipart/form-data.
 * @param {File} file The file to upload
 * @param {string} url The upload endpoint (e.g. http://localhost:8765/api/upload/avatar)
 * @returns {Promise<Object>} The JSON response from the server containing the final URL
 */
export async function uploadFile(file, url) {
    const formData = new FormData();
    formData.append('file', file);

    // We expect the server (FastAPI) to allow CORS for this origin
    const res = await fetch(url, {
        method: 'POST',
        body: formData,
    });

    if (!res.ok) {
        throw new Error(`Upload failed with status: ${res.status}`);
    }

    return await res.json();
}
