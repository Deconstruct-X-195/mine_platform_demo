/* ============ API 请求封装 ============ */
const API = {
  get token() { return localStorage.getItem('mc_token') || ''; },
  set token(v) { v ? localStorage.setItem('mc_token', v) : localStorage.removeItem('mc_token'); },

  async request(method, url, body, opts = {}) {
    const headers = {};
    if (this.token) headers['Authorization'] = 'Bearer ' + this.token;
    let payload;
    if (body instanceof FormData) {
      payload = body;
    } else if (body !== undefined && body !== null) {
      headers['Content-Type'] = 'application/json';
      payload = JSON.stringify(body);
    }
    const resp = await fetch(url, { method, headers, body: payload });
    if (opts.raw) return resp;
    let data = null;
    try { data = await resp.json(); } catch (_) { /* 非JSON */ }
    if (resp.status === 401 && !opts.silent) {
      this.token = '';
      location.hash = '#/login';
      Toast.error('登录已过期，请重新登录');
      throw new Error('unauthorized');
    }
    if (data && data.code !== 0) {
      if (!opts.silent) Toast.error(data.message || '请求失败');
      const err = new Error(data.message || '请求失败');
      err.code = data.code; err.resp = data;
      throw err;
    }
    return data && data.data;
  },
  get(url, params) {
    const q = params ? '?' + new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined)).toString() : '';
    return this.request('GET', url + q);
  },
  post(url, body, opts) { return this.request('POST', url, body, opts); },
  put(url, body, opts) { return this.request('PUT', url, body, opts); },
  del(url, body, opts) { return this.request('DELETE', url, body, opts); },

  /* 附件上传（多文件），返回 [{file_url, file_name}] */
  async upload(files, onProgress) {
    const out = [];
    for (const f of files) {
      const fd = new FormData();
      fd.append('file', f);
      const resp = await this.request('POST', '/api/upload', fd);
      out.push(resp);
      onProgress && onProgress(out.length, files.length);
    }
    return out;
  },

  /* 下载（Excel 导出等） */
  async download(url, params, filename) {
    const q = params ? '?' + new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined)).toString() : '';
    const resp = await fetch(url + q, { headers: { Authorization: 'Bearer ' + this.token } });
    if (!resp.ok) { Toast.error('导出失败'); return; }
    const blob = await resp.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename || 'export.xlsx';
    a.click();
    URL.revokeObjectURL(a.href);
    Toast.success('导出成功');
  }
};
