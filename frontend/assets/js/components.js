/* ============ 通用 UI 组件：数据表格 / 表单模态 / 上传 / 步骤条 / 详情 ============ */
const UI = {
  loading() {
    return el('div', { class: 'loading-mask' }, [
      el('div', { class: 'spinner' }), el('div', null, '加载中...')
    ]);
  },

  empty(text = '暂无数据') {
    return el('div', { class: 'empty' }, [el('div', { class: 'e-icon' }, '◌'), el('div', null, text)]);
  },

  /* DataTable: {columns:[{title,key,render,width}], fetch:(query)=>{list,total}, toolbar, query}
     返回 {root, reload} */
  table({ columns, fetch, toolbar, query = {}, pageSize = 10, rowKey = 'id' }) {
    const state = { page: 1, total: 0, query: { ...query } };
    const root = el('div', null);
    const tbody = el('tbody');
    const table = el('div', { class: 'table-wrap' },
      el('table', { class: 'tb' }, [
        el('thead', null, el('tr', null, columns.map(c =>
          el('th', { style: c.width ? { width: c.width } : null }, c.title)))),
        tbody
      ]));
    const pager = el('div', { class: 'pager' });
    const toolbarEl = el('div', { class: 'filter-bar' });
    if (toolbar) {
      const tb = toolbar.render ? toolbar.render(state) : toolbar;
      (Array.isArray(tb) ? tb : [tb]).forEach(n => n && toolbarEl.appendChild(n));
    }

    async function load() {
      tbody.innerHTML = '';
      tbody.appendChild(el('tr', null, el('td', { colspan: columns.length }, UI.loading())));
      pager.innerHTML = '';
      try {
        const res = await fetch({ ...state.query, page: state.page, page_size: pageSize });
        state.total = res.total;
        tbody.innerHTML = '';
        if (!res.list.length) {
          tbody.appendChild(el('tr', null, el('td', { colspan: columns.length }, UI.empty())));
        } else {
          res.list.forEach((row, idx) => {
            tbody.appendChild(el('tr', { 'data-key': row[rowKey] },
              columns.map(c => {
                const td = el('td', { class: c.strong ? 'strong' : (c.num ? 'num' : '') });
                const v = c.render ? c.render(row, idx) : (row[c.key] ?? '-');
                if (v instanceof Node) td.appendChild(v);
                else td.textContent = v ?? '-';
                return td;
              })));
          });
        }
        renderPager();
      } catch (e) {
        tbody.innerHTML = '';
        tbody.appendChild(el('tr', null, el('td', { colspan: columns.length }, UI.empty('加载失败'))));
      }
    }

    function renderPager() {
      const pages = Math.max(1, Math.ceil(state.total / pageSize));
      pager.innerHTML = '';
      pager.appendChild(el('span', null, `共 ${state.total} 条`));
      const prev = el('button', { onclick: () => { if (state.page > 1) { state.page--; load(); } }, disabled: state.page <= 1 }, '‹');
      const next = el('button', { onclick: () => { if (state.page < pages) { state.page++; load(); } }, disabled: state.page >= pages }, '›');
      pager.appendChild(prev);
      const from = Math.max(1, state.page - 2), to = Math.min(pages, from + 4);
      for (let p = from; p <= to; p++) {
        pager.appendChild(el('button', { class: p === state.page ? 'cur' : '', onclick: () => { state.page = p; load(); } }, p));
      }
      pager.appendChild(next);
    }

    root.appendChild(toolbarEl);
    root.appendChild(table);
    root.appendChild(pager);
    load();
    return { root, reload: load, state };
  },

  /* formDual: 多提交按钮表单 buttons:[{text, action, primary}], onSubmit(values, action) */
  formDual({ title, fields, buttons, onSubmit, wide, submitText }) {
    return new Promise(resolve => {
      const inputs = {};
      const body = el('div', null, el('div', { class: 'form-grid' },
        fields.map(f => this._field(f, inputs))));
      const footBtns = buttons.map(b => el('button', {
        class: `btn ${b.primary ? 'btn-primary' : ''}`,
        onclick: async () => {
          const values = this._collect(inputs);
          if (!values) return;
          try { await onSubmit(values, b.action); this._lastModal && this._lastModal.close(); resolve(values); }
          catch (e) { /* onSubmit 内部提示 */ }
        }
      }, b.text));
      this._lastModal = openModal({ title, wide, body, footer: close => footBtns });
    });
  },

  _field(f, inputs) {
    const readonly = false;
    const wrap = el('div', { class: `field${f.full ? ' full' : ''}` });
    const label = el('label', null, [f.label, f.required ? el('span', { class: 'req' }, '*') : null]);
    wrap.appendChild(label);
    let input;
    if (f.type === 'select') {
      input = el('select', { disabled: readonly },
        [el('option', { value: '' }, f.placeholder || '请选择'),
         ...(f.options || []).map(o => el('option', { value: o.value }, o.label))]);
    } else if (f.type === 'textarea') {
      input = el('textarea', { placeholder: f.placeholder || '', maxlength: f.maxlength || 500, disabled: readonly });
    } else if (f.type === 'file') {
      const filesBox = el('div', { class: 'file-list' });
      const fileStore = { files: [] };
      const box = el('div', { class: 'upload-box' }, '点击上传附件（PDF/图片）');
      const fileInput = el('input', { type: 'file', multiple: true, style: { display: 'none' } });
      box.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', async () => {
        if (!fileInput.files.length) return;
        try {
          const ups = await API.upload(Array.from(fileInput.files));
          fileStore.files.push(...ups);
          renderFiles();
          Toast.success('上传成功');
        } catch (e) { /* toast 已提示 */ }
        fileInput.value = '';
      });
      wrap.appendChild(fileInput);
      function renderFiles() {
        filesBox.innerHTML = '';
        fileStore.files.forEach((fi, i) => {
          filesBox.appendChild(el('div', { class: 'file-item' }, [
            el('span', null, '📄'),
            el('span', { class: 'fi-name' }, fi.file_name || fi.file_url),
            el('span', { class: 'fi-del', onclick: () => { fileStore.files.splice(i, 1); renderFiles(); } }, '删除')
          ]));
        });
      }
      (f.value || []).forEach(fi => fileStore.files.push(fi));
      renderFiles();
      wrap.appendChild(box);
      wrap.appendChild(filesBox);
      inputs[f.key] = { get: () => fileStore.files.map(f2 => ({ file_url: f2.file_url, file_name: f2.file_name })) };
      if (f.hint) wrap.appendChild(el('div', { class: 'hint' }, f.hint));
      return wrap;
    } else {
      input = el('input', { type: f.type === 'number' ? 'number' : (f.type === 'date' ? 'date' : 'text'),
        placeholder: f.placeholder || '', step: f.step || (f.type === 'number' ? '0.01' : null),
        min: f.min, max: f.max });
    }
    input.value = f.value ?? '';
    wrap.appendChild(input);
    if (f.hint) wrap.appendChild(el('div', { class: 'hint' }, f.hint));
    inputs[f.key] = {
      get: () => f.type === 'number' ? (input.value === '' ? null : Number(input.value)) : input.value.trim(),
      el: input, field: f
    };
    return wrap;
  },

  _collect(inputs) {
    let valid = true;
    const values = {};
    for (const [k, inp] of Object.entries(inputs)) {
      const v = inp.get();
      values[k] = v;
      if (inp.field && inp.field.required) {
        const empty = Array.isArray(v) ? !v.length : (v === null || v === '' || v === undefined);
        if (inp.el && inp.el.parentElement) inp.el.parentElement.classList.toggle('invalid', empty);
        if (empty) valid = false;
      }
    }
    if (!valid) { Toast.error('请填写完整必填项'); return null; }
    return values;
  },

  /* FormModal: fields: [{key,label,type(text/number/select/date/textarea/file),options,required,value,full,hint,placeholder,min,max}]
     返回 Promise<values>（resolve on submit，校验失败不关闭） */
  form({ title, fields, submitText = '提交', onSubmit, wide, readonly = false }) {
    return new Promise(resolve => {
      const inputs = {};
      const body = el('div', null, el('div', { class: 'form-grid' },
        fields.map(f => {
          const wrap = el('div', { class: `field${f.full ? ' full' : ''}` });
          const label = el('label', null, [f.label, f.required && !readonly ? el('span', { class: 'req' }, '*') : null]);
          wrap.appendChild(label);
          let input;
          if (f.type === 'select') {
            input = el('select', { disabled: readonly },
              [el('option', { value: '' }, f.placeholder || '请选择'),
               ...(f.options || []).map(o => el('option', { value: o.value }, o.label))]);
          } else if (f.type === 'textarea') {
            input = el('textarea', { placeholder: f.placeholder || '', maxlength: f.maxlength || 500, disabled: readonly });
          } else if (f.type === 'file') {
            const filesBox = el('div', { class: 'file-list' });
            const fileStore = { files: [] };
            const box = el('div', { class: 'upload-box' }, readonly ? '无附件' : '点击或拖拽上传附件');
            if (!readonly) {
              const fileInput = el('input', { type: 'file', multiple: true, style: { display: 'none' } });
              box.addEventListener('click', () => fileInput.click());
              fileInput.addEventListener('change', async () => {
                if (!fileInput.files.length) return;
                try {
                  const ups = await API.upload(Array.from(fileInput.files));
                  fileStore.files.push(...ups);
                  renderFiles();
                  Toast.success('上传成功');
                } catch (e) { /* toast 已提示 */ }
                fileInput.value = '';
              });
              wrap.appendChild(fileInput);
            }
            function renderFiles() {
              filesBox.innerHTML = '';
              fileStore.files.forEach((fi, i) => {
                filesBox.appendChild(el('div', { class: 'file-item' }, [
                  el('span', null, '📄'),
                  el('span', { class: 'fi-name' }, fi.file_name || fi.file_url),
                  !readonly ? el('span', { class: 'fi-del', onclick: () => { fileStore.files.splice(i, 1); renderFiles(); } }, '删除') : null
                ]));
              });
            }
            (f.value || []).forEach(fi => fileStore.files.push(fi));
            renderFiles();
            wrap.appendChild(box);
            wrap.appendChild(filesBox);
            inputs[f.key] = { get: () => fileStore.files.map(f2 => ({ file_url: f2.file_url, file_name: f2.file_name })) };
            if (!readonly && f.hint) wrap.appendChild(el('div', { class: 'hint' }, f.hint));
            return wrap;
          } else {
            input = el('input', { type: f.type === 'number' ? 'number' : (f.type === 'date' ? 'date' : 'text'),
              placeholder: f.placeholder || '', value: f.value ?? '', step: f.step || (f.type === 'number' ? '0.01' : null),
              min: f.min, max: f.max, disabled: readonly });
          }
          input.value = f.value ?? '';
          wrap.appendChild(input);
          if (f.hint && !readonly) wrap.appendChild(el('div', { class: 'hint' }, f.hint));
          inputs[f.key] = {
            get: () => f.type === 'number' ? (input.value === '' ? null : Number(input.value)) : input.value.trim(),
            el: input, field: f
          };
          return wrap;
        })));

      const md = openModal({
        title, wide, body,
        footer: close => readonly ? [
          el('button', { class: 'btn', onclick: close }, '关闭')
        ] : [
          el('button', { class: 'btn', onclick: close }, '取消'),
          el('button', {
            class: 'btn btn-primary',
            onclick: async () => {
              // 校验
              let valid = true;
              const values = {};
              for (const [k, inp] of Object.entries(inputs)) {
                const v = inp.get();
                values[k] = v;
                if (inp.field && inp.field.required) {
                  const empty = Array.isArray(v) ? !v.length : (v === null || v === '' || v === undefined);
                  inp.el && inp.el.parentElement.classList.toggle('invalid', empty);
                  if (empty) valid = false;
                }
              }
              if (!valid) { Toast.error('请填写完整必填项'); return; }
              try {
                await onSubmit(values);
                close();
                resolve(values);
              } catch (e) { /* onSubmit 内部处理提示 */ }
            }
          }, submitText)
        ]
      });
      return md;
    });
  },

  /* 详情模态：sections: [{title, items:[{label, value|render, full}]}] */
  detail({ title, sections, wide }) {
    const body = el('div', null);
    sections.forEach(sec => {
      body.appendChild(el('div', { class: 'card-title' }, sec.title));
      const grid = el('div', { class: 'desc-grid' });
      sec.items.forEach(it => {
        const v = it.render ? it.render() : (it.value ?? '-');
        const dv = el('div', { class: 'd-value' });
        if (v instanceof Node) dv.appendChild(v); else dv.textContent = v;
        grid.appendChild(el('div', { class: `desc-item${it.full ? ' full' : ''}` }, [
          el('div', { class: 'd-label' }, it.label), dv
        ]));
      });
      body.appendChild(grid);
    });
    openModal({ title, body, wide, footer: close => [el('button', { class: 'btn', onclick: close }, '关闭')] });
  },

  /* 物流/流程步骤条 steps: [{code,name,time,done,cur}] */
  steps(steps) {
    return el('div', { class: 'steps' },
      steps.map(s => el('div', { class: `step${s.done ? ' done' : ''}${s.cur ? ' cur' : ''}` }, [
        el('div', { class: 'dot' }, s.done ? '✓' : (s.code ?? '')),
        el('div', { class: 'lbl' }, s.name),
        s.time ? el('div', { class: 'tme' }, s.time) : null
      ])));
  }
};

/* 上传文件选择框（用于详情等只读附件展示） */
function fileLinks(files) {
  if (!files || !files.length) return '-';
  const wrap = el('div', { class: 'file-list' });
  files.forEach(f => wrap.appendChild(el('div', { class: 'file-item' }, [
    el('span', null, '📄'),
    el('a', { href: f.file_url, target: '_blank' }, f.file_name || f.file_url)
  ])));
  return wrap;
}
