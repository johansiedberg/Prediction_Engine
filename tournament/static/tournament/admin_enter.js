document.addEventListener('DOMContentLoaded', function() {
    // Target the admin change form
    const form = document.querySelector('#tournament_form') || document.querySelector('form');
    
    if (form) {
        form.addEventListener('keydown', function(event) {
            // Check if the pressed key is Enter
            if (event.key === 'Enter') {
                // Do not intercept if user is typing in a textarea, clicking a button, or using dropdowns (like Select2)
                if (event.target.tagName === 'TEXTAREA' || event.target.tagName === 'BUTTON' || event.target.type === 'submit') {
                    return;
                }
                if (event.target.closest('.select2-container')) {
                    return;
                }
                
                // Prevent default form submission and click "Save and continue editing" instead
                event.preventDefault();
                const continueBtn = document.querySelector('input[name="_continue"]');
                if (continueBtn) {
                    continueBtn.click();
                }
            }
        });
    }
});