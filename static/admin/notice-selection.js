document.querySelectorAll('[data-recipient-action]').forEach(button => {

    button.addEventListener('click', () => {

        const group = button.closest('.recipient-group');

        const checked = button.dataset.recipientAction === 'all';

        group.querySelectorAll('input[name="recipients"]').forEach(input => {
            input.checked = checked;
        });

        updateRecipientCount();

    });

});