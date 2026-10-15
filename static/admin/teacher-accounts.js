function filterTeacherRows() {
    const search = document.getElementById("teacher-search");
    const noMatch = document.getElementById("teacher-no-match");

    if (!search) return;

    const query = search.value.trim().toLowerCase();
    let visible = 0;

    document.querySelectorAll("[data-teacher-row]").forEach(row => {
        const text = (row.dataset.search || "").toLowerCase();

        row.hidden = !text.includes(query);

        if (!row.hidden) visible++;
    });

    if (noMatch) {
        noMatch.hidden = visible > 0;
    }
}

document.getElementById("teacher-search")
    ?.addEventListener("input", filterTeacherRows);

filterTeacherRows();


document.addEventListener("submit", async event => {
    const form = event.target;

    if (!(form instanceof HTMLFormElement)) return;
    if (!form.matches("[data-teacher-form]")) return;

    event.preventDefault();

    const button = form.querySelector('button[type="submit"]');

    if (!button || button.disabled) return;

    let message = document.getElementById(form.dataset.message);

    // Create a message area if it is missing.
    if (!message) {
        message = document.createElement("p");
        message.className = "notice";
        message.setAttribute("role", "status");
        message.setAttribute("aria-live", "polite");
        message.hidden = true;

        if (form.dataset.message) {
            message.id = form.dataset.message;
        }

        const tableWrap = form.closest(".table-wrap");

        if (tableWrap) {
            tableWrap.before(message);
        } else {
            form.prepend(message);
        }
    }

    const originalHTML = button.innerHTML;
    const controller = new AbortController();
    let timeout;

    try {
        const body = new FormData(form);

        button.disabled = true;
        button.textContent = "Saving...";
        message.hidden = true;

        timeout = setTimeout(() => controller.abort(), 15000);

        const response = await fetch(form.action, {
            method: "POST",
            body: body,
            credentials: "same-origin",
            signal: controller.signal,
            headers: {
                "Accept": "application/json"
            }
        });

        if (response.redirected) {
            throw new Error("Please sign in again and retry.");
        }

        const contentType =
            response.headers.get("content-type") || "";

        if (!contentType.includes("application/json")) {
            throw new Error(
                `Request failed (${response.status}). Refresh the page and retry.`
            );
        }

        const data = await response.json();

        if (!response.ok || !data.ok) {
            throw new Error(
                data.message || "Could not save the changes."
            );
        }

        // Update the teacher list after creating or changing status.
        if (typeof data.html === "string") {
            const list = document.getElementById("teacher-list");

            if (list) {
                list.innerHTML = data.html;
                filterTeacherRows();

                const total =
                    document.querySelector(".teacher-total");

                if (total) {
                    total.textContent = list.querySelectorAll(
                        "[data-teacher-row]"
                    ).length;
                }
            }
        }

        // Update account settings.
        if (data.name !== undefined) {
            const nameLabel =
                document.querySelector("[data-teacher-name]");

            if (nameLabel) {
                nameLabel.textContent = data.name;
            }

            const nameInput = form.elements.namedItem("name");
            const emailInput = form.elements.namedItem("email");

            if (nameInput) nameInput.value = data.name;
            if (emailInput) emailInput.value = data.email;
        }

        if (form.hasAttribute("data-clear-on-success")) {
            form.reset();
        }

        message.className = "notice success";
        message.textContent =
            data.message || "Saved successfully.";
        message.hidden = false;

    } catch (error) {
        message.className = "notice danger";

        message.textContent = error.name === "AbortError"
            ? "Request timed out. Refresh to check the current status before retrying."
            : error.message || "Could not save. Please retry.";

        message.hidden = false;

    } finally {
        clearTimeout(timeout);
        button.disabled = false;
        button.innerHTML = originalHTML;
    }
});