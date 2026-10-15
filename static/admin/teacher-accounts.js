function filterTeacherRows() {
    const search = document.getElementById('teacher-search');

    if (!search) return;

    const query = search.value.trim().toLowerCase();
    let visible = 0;

    document.querySelectorAll('[data-teacher-row]').forEach(row => {
        row.hidden = !row.dataset.search.toLowerCase().includes(query);

        if (!row.hidden) visible++;
    });

    document.getElementById('teacher-no-match').hidden = visible > 0;
}

document.getElementById('teacher-search')
    ?.addEventListener('input', filterTeacherRows);

filterTeacherRows();


document.addEventListener('submit', async event => {
    const form = event.target;

    if (!form.matches('[data-teacher-form]')) return;

    event.preventDefault();

    const button = form.querySelector('button[type="submit"]');

    if (button.disabled) return;

    const message = document.getElementById(form.dataset.message);
    const originalText = button.textContent;
    const body = new FormData(form);

    button.disabled = true;
    button.textContent = 'Saving...';
    message.hidden = true;

    try {
        const response = await fetch(form.getAttribute('action'), {
            method: 'POST',
            body,
            credentials: 'same-origin',
            headers: {
                'Accept': 'application/json'
            }
        });

        if (response.redirected) {
            throw new Error('Please sign in again and retry.');
        }

        const contentType = response.headers.get('content-type') || '';

        if (!contentType.includes('application/json')) {
            throw new Error(
                `Request failed (${response.status}). Refresh the page and try again.`
            );
        }

        const data = await response.json();

        if (!response.ok || !data.ok) {
            throw new Error(data.message || 'Could not save.');
        }

        if (data.html !== undefined) {
            document.getElementById('teacher-list').innerHTML = data.html;
            document.getElementById('teacher-search').value = '';
            filterTeacherRows();
        }

        if (data.name) {
            document.querySelector('[data-teacher-name]').textContent = data.name;

            form.elements.namedItem('name').value = data.name;
            form.elements.namedItem('email').value = data.email;
        }

        if (form.hasAttribute('data-clear-on-success')) {
            form.reset();
        }

        message.className = 'notice success';
        message.textContent = data.message;
        message.hidden = false;

    } catch (error) {
        message.className = 'notice danger';
        message.textContent = error.message;
        message.hidden = false;

    } finally {
        button.disabled = false;
        button.textContent = originalText;
    }
});