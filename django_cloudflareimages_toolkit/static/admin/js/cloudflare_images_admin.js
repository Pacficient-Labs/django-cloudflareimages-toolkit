/**
 * JavaScript for Cloudflare Images Django Admin
 */

(function($) {
    'use strict';

    // Check status function for individual images
    window.checkStatus = function(imageId) {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
        
        fetch(`/admin/django_cloudflare_images/cloudflareimage/${imageId}/check_status/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                alert('Failed to check status: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to check status');
        });
    };

    // Auto-refresh functionality for pending/draft images
    function autoRefreshStatus() {
        const pendingRows = document.querySelectorAll('tr[data-status="pending"], tr[data-status="draft"]');
        if (pendingRows.length > 0) {
            console.log(`Auto-refreshing ${pendingRows.length} pending/draft images`);
            // Refresh every 30 seconds if there are pending images
            setTimeout(() => {
                location.reload();
            }, 30000);
        }
    }

    // Initialize when DOM is ready
    $(document).ready(function() {
        // Add status data attributes to table rows for auto-refresh
        $('.result_list tbody tr').each(function() {
            const statusCell = $(this).find('td').eq(2); // Status is 3rd column
            const statusText = statusCell.text().toLowerCase().trim();
            $(this).attr('data-status', statusText);
        });

        // Start auto-refresh if needed
        autoRefreshStatus();

        // Add copy functionality to Cloudflare IDs
        $('.cloudflare-id-copy').on('click', function() {
            const text = $(this).data('id');
            navigator.clipboard.writeText(text).then(function() {
                $(this).css('background-color', '#90EE90');
                setTimeout(() => {
                    $(this).css('background-color', '');
                }, 1000);
            });
        });

        // Add image preview modal functionality
        $('.image-preview-trigger').on('click', function(e) {
            e.preventDefault();
            const imageUrl = $(this).data('url');
            const modal = $(`
                <div class="image-preview-modal" style="
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(0,0,0,0.8);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 10000;
                    cursor: pointer;
                ">
                    <img src="${imageUrl}" style="
                        max-width: 90%;
                        max-height: 90%;
                        border-radius: 8px;
                        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
                    ">
                </div>
            `);
            
            $('body').append(modal);
            
            modal.on('click', function() {
                modal.remove();
            });
        });

        // Bulk actions enhancement
        $('#changelist-form').on('submit', function(e) {
            const action = $('select[name="action"]').val();
            const selectedCount = $('input[name="_selected_action"]:checked').length;
            
            if (selectedCount === 0) {
                alert('Please select at least one image.');
                e.preventDefault();
                return false;
            }
            
            if (action === 'delete_from_cloudflare_action') {
                if (!confirm(`Are you sure you want to delete ${selectedCount} image(s) from Cloudflare? This action cannot be undone.`)) {
                    e.preventDefault();
                    return false;
                }
            }
        });

        // Add status indicators
        $('.status-indicator').each(function() {
            const status = $(this).text().toLowerCase();
            const colors = {
                'pending': '#ffc107',
                'draft': '#17a2b8',
                'uploaded': '#28a745',
                'failed': '#dc3545',
                'expired': '#6c757d'
            };
            
            if (colors[status]) {
                $(this).css({
                    'color': colors[status],
                    'font-weight': 'bold'
                });
            }
        });
    });

})(django.jQuery);
