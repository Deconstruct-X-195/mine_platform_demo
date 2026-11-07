/* API 封装：统一响应体处理、JWT 携带、业务错误提示 */
(function () {
  const TOKEN_KEY = 'mine_token';
  const USER_KEY = 'mine_user';

  async function request(method, path, body, opts) {
    opts = opts || {};
    const headers = {};
    if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) headers['Authorization'] = 'Bearer ' + token;
    let resp;
    try {
      resp = await fetch('/api/v1' + path, {
        method, headers,
        body: body === undefined ? undefined
          : (body instanceof FormData ? body : JSON.stringify(body)),
      });
    } catch (e) {
      UI.toast('网络异常，请检查服务是否启动', 'err');
      throw e;
    }
    let data = null;
    try { data = await resp.json(); } catch (e) { /* 空响应体 */ }
    if (resp.status === 401 && !opts.silent) {
      clearAuth();
      location.hash = '#/login';
      UI.toast((data && data.message) || '登录已过期', 'err');
      throw new Error('401');
    }
    if (!resp.ok || (data && data.code !== 0)) {
      const msg = (data && data.message) || ('HTTP ' + resp.status);
      if (!opts.silent) UI.toast(msg, 'err');
      const err = new Error(msg);
      err.code = data && data.code;
      err.http = resp.status;
      throw err;
    }
    return data ? data.data : null;
  }

  function clearAuth() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function saveAuth(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function currentUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch (e) { return null; }
  }

  function token() { return localStorage.getItem(TOKEN_KEY); }

  window.API = {
    get: (p, opts) => request('GET', p, undefined, opts),
    post: (p, b, opts) => request('POST', p, b, opts),
    put: (p, b, opts) => request('PUT', p, b, opts),
    del: (p, opts) => request('DELETE', p, undefined, opts),
    upload(file) {
      const fd = new FormData();
      fd.append('file', file);
      return request('POST', '/files', fd);
    },
    async download(path, filename) {
      const headers = {};
      const tk = localStorage.getItem(TOKEN_KEY);
      if (tk) headers['Authorization'] = 'Bearer ' + tk;
      const resp = await fetch('/api/v1' + path, { headers });
      if (!resp.ok) { UI.toast('下载失败（HTTP ' + resp.status + '）', 'err'); return; }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || 'download';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    },
    downloadFile(fileId, fileName) {
      if (fileId == null || fileId === '') return;
      return API.download('/files/' + fileId, fileName || String(fileId));
    },
    saveAuth, clearAuth, currentUser, token,
    qs(params) {
      const s = Object.entries(params || {}).filter(([, v]) => v !== '' && v != null)
        .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
      return s ? '?' + s : '';
    },
  };
})();
