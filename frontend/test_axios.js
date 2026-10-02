import axios from 'axios';
import FormData from 'form-data';

const form = new FormData();
form.append('file', Buffer.from('hello'), { filename: 'test.txt', contentType: 'text/plain' });
form.append('case_id', 'case-123');
form.append('original_filename', 'test.txt');
form.append('original_mime_type', 'text/plain');
form.append('original_sha256', 'hash');
form.append('encryption_algorithm', 'NONE');

// What if we don't append iv at all?
// form.append('iv', ''); // missing
form.append('wrapped_deks', '[]');

axios.post('http://localhost:8000/evidence/upload', form, {
    headers: form.getHeaders()
}).then(res => console.log(res.status)).catch(err => console.log(err.response?.status, err.response?.data));
