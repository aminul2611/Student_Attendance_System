(() => {
    const form = document.getElementById("notice-form");

    if (!form) return;

    const search = document.getElementById("recipient-search");
    const classSelect = document.getElementById("notice-student-class");
    const count = document.getElementById("recipient-count");

    const groups = Array.from(
        form.querySelectorAll(".recipient-group")
    );

    function updateRecipientCount() {
        if (!count) return;

        count.textContent = form.querySelectorAll(
            'input[name="recipients"]:checked'
        ).length;
    }

    function filterRecipients() {
        const query = (search?.value || "")
            .trim()
            .toLocaleLowerCase();

        const selectedClass = classSelect?.value || "";

        groups.forEach(group => {
            let visible = 0;
            const isStudents =
                group.dataset.recipientRole === "student";

            group.querySelectorAll(".recipient-option").forEach(row => {
                const text = (row.dataset.search || "")
                    .toLocaleLowerCase();

                const classIds = (row.dataset.classIds || "")
                    .split(",")
                    .filter(Boolean);

                let matchesClass = true;

                if (isStudents && selectedClass === "unassigned") {
                    matchesClass = classIds.length === 0;
                } else if (isStudents && selectedClass) {
                    matchesClass = classIds.includes(selectedClass);
                }

                row.hidden = !(
                    text.includes(query) && matchesClass
                );

                if (!row.hidden) visible++;
            });

            const empty = group.querySelector(
                ".recipient-no-results"
            );

            if (empty) empty.hidden = visible > 0;
        });

        updateRecipientCount();
    }

    form.querySelectorAll("[data-recipient-action]").forEach(button => {
        button.addEventListener("click", () => {
            const group = button.closest(".recipient-group");

            if (!group) return;

            const checked =
                button.dataset.recipientAction === "all";

            group.querySelectorAll(".recipient-option").forEach(row => {
                if (row.hidden) return;

                const input = row.querySelector(
                    'input[name="recipients"]'
                );

                if (input && !input.disabled) {
                    input.checked = checked;
                }
            });

            updateRecipientCount();
        });
    });

    form.addEventListener("change", event => {
        if (event.target.matches('input[name="recipients"]')) {
            updateRecipientCount();
        }
    });

    search?.addEventListener("input", filterRecipients);
    classSelect?.addEventListener("change", filterRecipients);

    form.addEventListener("reset", () => {
        requestAnimationFrame(filterRecipients);
    });

    filterRecipients();
})();