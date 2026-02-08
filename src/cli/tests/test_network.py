# Tests for O3DE Pilot Network module
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for network connectivity detection."""

import pytest
from unittest.mock import patch, MagicMock


class TestNetworkStatus:
    """Tests for NetworkStatus class."""
    
    def test_is_online_returns_bool(self):
        """Test that is_online returns a boolean."""
        from o3de_pilot.core.network import is_online
        
        result = is_online()
        assert isinstance(result, bool)
    
    def test_is_offline_opposite_of_online(self):
        """Test that is_offline is opposite of is_online."""
        from o3de_pilot.core.network import is_online, is_offline
        
        online = is_online()
        offline = is_offline()
        assert online != offline
    
    def test_set_offline_for_testing(self):
        """Test that we can force offline mode for testing."""
        from o3de_pilot.core.network import NetworkStatus, is_online
        
        # Save original state
        original = is_online()
        
        # Force offline
        NetworkStatus.set_offline_for_testing(offline=True)
        assert is_online() is False
        
        # Force online
        NetworkStatus.set_offline_for_testing(offline=False)
        assert is_online() is True
        
        # Restore by forcing a check (reset cache time)
        NetworkStatus._last_check = 0
    
    def test_listener_notification(self):
        """Test that listeners are notified of status changes."""
        from o3de_pilot.core.network import NetworkStatus
        
        callback_results = []
        def callback(is_online: bool):
            callback_results.append(is_online)
        
        # Add listener
        NetworkStatus.add_listener(callback)
        
        try:
            # Force a status change
            NetworkStatus.set_offline_for_testing(offline=True)
            assert len(callback_results) >= 1
            assert callback_results[-1] is False
            
            NetworkStatus.set_offline_for_testing(offline=False)
            assert len(callback_results) >= 2
            assert callback_results[-1] is True
        finally:
            # Clean up
            NetworkStatus.remove_listener(callback)
            NetworkStatus._last_check = 0  # Reset cache
    
    @patch('socket.socket')
    def test_check_connectivity_with_mock(self, mock_socket_class):
        """Test connectivity check with mocked socket."""
        from o3de_pilot.core.network import NetworkStatus
        
        # Set up mock socket
        mock_socket = MagicMock()
        mock_socket.connect_ex.return_value = 0  # Success
        mock_socket_class.return_value = mock_socket
        
        # Reset cache to force fresh check
        NetworkStatus._last_check = 0
        
        # Check connectivity
        result = NetworkStatus._check_connectivity(timeout=1.0)
        assert result is True
        
        # Verify socket was used correctly
        assert mock_socket.settimeout.called
        assert mock_socket.connect_ex.called
        assert mock_socket.close.called
    
    @patch('socket.socket')
    def test_check_connectivity_failure(self, mock_socket_class):
        """Test connectivity check when all hosts fail."""
        from o3de_pilot.core.network import NetworkStatus
        
        # Set up mock socket that always fails
        mock_socket = MagicMock()
        mock_socket.connect_ex.return_value = 1  # Failure
        mock_socket_class.return_value = mock_socket
        
        # Check connectivity
        result = NetworkStatus._check_connectivity(timeout=1.0)
        assert result is False
