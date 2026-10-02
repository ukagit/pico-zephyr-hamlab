#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/socket.h>
#include <zephyr/shell/shell.h>
#include <zephyr/shell/shell_dummy.h>
#include <zephyr/sys/printk.h>
#include "../hamlab_version.h"



#define TCP_CONSOLE_PORT 23
#define TCP_CONSOLE_STACK_SIZE 4096
#define TCP_CONSOLE_LINE_SIZE 256
#define TCP_CONSOLE_RETRY_MS 500

static int send_all(int fd, const void *data, size_t length)
{
	const uint8_t *cursor = data;

	while (length > 0U) {
		ssize_t sent = zsock_send(fd, cursor, length, 0);
		if (sent <= 0) {
			return sent == 0 ? -ECONNRESET : -errno;
		}
		cursor += sent;
		length -= (size_t)sent;
	}
	return 0;
}

static int send_text(int fd, const char *text)
{
	return send_all(fd, text, strlen(text));
}

static int execute_line(int client, const char *line)
{
	const struct shell *dummy = shell_backend_dummy_get_ptr();
	const char *output;
	size_t output_size = 0U;
	int rc;

	if (dummy == NULL) {
		return send_text(client, "ERROR: shell backend unavailable\r\n");
	}

	shell_backend_dummy_clear_output(dummy);
	rc = shell_execute_cmd(dummy, line);
	output = shell_backend_dummy_get_output(dummy, &output_size);
	if (output != NULL && output_size > 0U) {
		int send_rc = send_all(client, output, output_size);
		if (send_rc != 0) {
			return send_rc;
		}
	}
	if (rc != 0 && output_size == 0U) {
		char error[48];
		int count = snprintk(error, sizeof(error),
				     "command returned %d\r\n", rc);
		if (count > 0) {
			return send_all(client, error, (size_t)count);
		}
	}
	return 0;
}

static int serve_client(int client)
{
	char line[TCP_CONSOLE_LINE_SIZE];
	size_t used = 0U;
	bool skip_lf = false;
	unsigned int iac_bytes = 0U;
	char banner[128];
	int count;

	count = snprintk(banner, sizeof(banner),
			"\r\n%s %s TCP console\r\n"
			"Type 'help' for commands.\r\n\r\ntcp:~$ ",
			"HamLab", HAMLAB_VERSION);
	if (count <= 0 || send_all(client, banner, (size_t)count) != 0) {
		return -EIO;
	}

	while (true) {
		uint8_t input[64];
		ssize_t received = zsock_recv(client, input, sizeof(input), 0);

		if (received <= 0) {
			return received == 0 ? 0 : -errno;
		}

		for (ssize_t pos = 0; pos < received; ++pos) {
			uint8_t ch = input[pos];

			/* Ignore three-byte Telnet IAC negotiations from host clients. */
			if (iac_bytes > 0U) {
				iac_bytes--;
				continue;
			}
			if (ch == 0xffU) {
				iac_bytes = 2U;
				continue;
			}

			if (ch == '\n' && skip_lf) {
				skip_lf = false;
				continue;
			}
			skip_lf = false;

			if (ch == '\r' || ch == '\n') {
				line[used] = '\0';
				if (ch == '\r') {
					skip_lf = true;
				}
				if (used > 0U && execute_line(client, line) != 0) {
					return -EIO;
				}
				used = 0U;
				if (send_text(client, "tcp:~$ ") != 0) {
					return -EIO;
				}
				continue;
			}

			if (ch == 0x08U || ch == 0x7fU) {
				if (used > 0U) {
					used--;
				}
				continue;
			}

			if (ch >= 0x20U && ch < 0x7fU &&
			    used < sizeof(line) - 1U) {
				line[used++] = (char)ch;
			}
		}
	}
}

static void tcp_console_thread(void *arg1, void *arg2, void *arg3)
{
	struct sockaddr_in address = {
		.sin_family = AF_INET,
		.sin_port = htons(TCP_CONSOLE_PORT),
		.sin_addr.s_addr = htonl(INADDR_ANY),
	};
	int server = -1;
	int reuse = 1;

	ARG_UNUSED(arg1);
	ARG_UNUSED(arg2);
	ARG_UNUSED(arg3);

	while (net_if_get_default() == NULL ||
	       net_if_oper_state(net_if_get_default()) != NET_IF_OPER_UP) {
		k_sleep(K_MSEC(TCP_CONSOLE_RETRY_MS));
	}

	server = zsock_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
	if (server < 0) {
		printk("TCP console socket failed: %d\n", errno);
		return;
	}
	(void)zsock_setsockopt(server, SOL_SOCKET, SO_REUSEADDR,
			       &reuse, sizeof(reuse));
	if (zsock_bind(server, (struct sockaddr *)&address, sizeof(address)) < 0 ||
	    zsock_listen(server, 1) < 0) {
		printk("TCP console listen failed: %d\n", errno);
		zsock_close(server);
		return;
	}

	printk("TCP console ready on port %d\n", TCP_CONSOLE_PORT);
	while (true) {
		int client = zsock_accept(server, NULL, NULL);
		if (client < 0) {
			k_sleep(K_MSEC(TCP_CONSOLE_RETRY_MS));
			continue;
		}
		(void)serve_client(client);
		zsock_close(client);
	}
}

K_THREAD_DEFINE(tcp_console_id, TCP_CONSOLE_STACK_SIZE, tcp_console_thread,
		NULL, NULL, NULL, 12, 0, 0);
