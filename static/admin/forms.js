function updateRecipientCount() {
    const counter = document.getElementById(
        "recipient-count"
    );

    if (counter) {
        counter.textContent = document.querySelectorAll(
            '#notice-form input[name="recipients"]:checked'
        ).length;
    }
}

document.addEventListener("change", (event) => {
    if (event.target.matches('input[name="recipients"]')) {
        updateRecipientCount();
    }
});

document.getElementById("recipient-search")
    ?.addEventListener("input", (event) => {
        const query = event.target.value
            .trim()
            .toLowerCase();

        document.querySelectorAll(".recipient-option")
            .forEach(item => {
                item.hidden = !item.dataset.search
                    .toLowerCase()
                    .includes(query);
            });
    });

updateRecipientCount();

document.addEventListener("submit", async (event) => {
    const form = event.target;

    if (!form.matches("[data-ajax-form]")) {
        return;
    }

    event.preventDefault();

    const button = form.querySelector(
        'button[type="submit"]'
    );

    if (button.disabled) {
        return;
    }

    if (
        form.hasAttribute("data-confirm-delete")
        && form.dataset.confirmed !== "yes"
    ) {
        form.dataset.confirmed = "yes";
        button.textContent = "Confirm delete";

        setTimeout(() => {
            if (button.isConnected && !button.disabled) {
                delete form.dataset.confirmed;
                button.textContent = "Delete";
            }
        }, 5000);

        return;
    }

    const message = document.getElementById(
        form.dataset.message
    );

    const originalText = button.textContent;
    const body = new FormData(form);

    button.disabled = true;
    button.textContent = "Saving...";
    message.hidden = true;

    try {
        const response = await fetch(form.getAttribute('action'), {
            method: "POST",
            body,
            credentials: "same-origin",
            headers: {
                "Accept": "application/json"
            }
        });

        const contentType = response.headers.get(
            "content-type"
        ) || "";

        if (!contentType.includes("application/json")) {
            throw new Error(
                "Could not save. Refresh the page and try again; sign in if needed."
            );
        }

        const data = await response.json();

        if (!response.ok || !data.ok) {
            throw new Error(
                data.message || "Could not save."
            );
        }

        message.className = "notice success";
        message.textContent = data.message;
        message.hidden = false;

        if (data.name) {
            const label = document.querySelector(
                ".header-right b"
            );

            const avatar = document.querySelector(
                ".admin-avatar"
            );

            if (label) {
                label.textContent = data.name;
            }

            if (avatar) {
                avatar.textContent = data.name
                    .slice(0, 1)
                    .toUpperCase();
            }

            form.elements.namedItem("name").value =
                data.name;
        }

        if (data.html !== undefined) {
            document.getElementById(
                "notice-list"
            ).innerHTML = data.html;
        }

        if (form.dataset.reset === "password") {
            form.reset();
        }

        const editor = document.getElementById(
            "notice-form"
        );

        const deletedEditingNotice =
            editor
            && data.deleted_id
            && editor.elements.namedItem(
                "notice_id"
            ).value === String(data.deleted_id);

        if (
            form.dataset.reset === "notice"
            || deletedEditingNotice
        ) {
            for (const key of [
                "notice_id",
                "title",
                "body"
            ]) {
                editor.elements.namedItem(key).value = "";
            }

            editor.elements.namedItem("active").value = "1";

            editor.querySelectorAll(
                'input[name="recipients"]'
            ).forEach(input => {
                input.checked = false;
            });

            document.getElementById(
                "recipient-search"
            ).value = "";

            document.querySelectorAll(
                ".recipient-option"
            ).forEach(item => {
                item.hidden = false;
            });

            updateRecipientCount();

            window.history.replaceState(
                null,
                "",
                editor.dataset.pageUrl
            );

            document.getElementById(
                "notice-form-heading"
            ).textContent = "Create notice";

            document.getElementById(
                "cancel-notice-edit"
            ).hidden = true;
        }

    } catch (error) {
        message.className = "notice danger";
        message.textContent = error.message;
        message.hidden = false;

    } finally {
        button.disabled = false;
        button.textContent = originalText;
        delete form.dataset.confirmed;
    }
});