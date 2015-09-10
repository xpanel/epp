

/* mod_whois 								*
 *									*
 * version 0.1								*
 * Alexander Mayrhofer <axelm@nic.at>					*
 * 									*
 * please see LICENSE for licensing issues				*/



#include "httpd.h"
#define CORE_PRIVATE
#include "http_protocol.h"
#include "http_config.h"
#include "http_connection.h"
#include "http_core.h"
#include "http_request.h"
#include "ap_config.h"
#include "apr_strings.h"
#include "apr_pools.h"
#include "apr_buckets.h"
#include "apr_general.h"
#include "util_filter.h"
#include "scoreboard.h"
#include <sys/types.h>

#define DEFAULT_URI "GET /whois/whois.php?domain="

module AP_MODULE_DECLARE_DATA whois_module;

typedef struct whois_conn_rec {
        int whois_on;
        const char *whois_prefix;
} whois_conn_rec;


static void *whois_create_server(apr_pool_t *p, server_rec *s)
{
	whois_conn_rec	*conf = (whois_conn_rec*)apr_pcalloc(p, sizeof(*conf));
	conf->whois_on = 0;
	conf->whois_prefix = DEFAULT_URI;
	return conf;
}

static const char *whois_on(cmd_parms *cmd, void *dummy, int arg)
{
	whois_conn_rec *conf = ap_get_module_config(cmd->server->module_config,
		&whois_module);
	conf->whois_on = arg;
	return NULL;
}

static const char *whois_prefix(cmd_parms *cmd, void *dummy, const char *arg)
{
	whois_conn_rec *conf = ap_get_module_config(cmd->server->module_config,
		&whois_module);
	conf->whois_prefix = arg;
	return NULL;
}

apr_status_t whois_input_filter(ap_filter_t *f, apr_bucket_brigade *b,
		ap_input_mode_t mode, apr_read_type_e block,
		apr_off_t readbytes)
{
	apr_bucket *e;
	apr_status_t rv;
	whois_conn_rec *conf;
	const char *original;
	char *quoted;
	char *crlfpos;
	apr_size_t len;
	
	if (mode != AP_MODE_GETLINE) {
		return ap_get_brigade(f->next, b, mode, block, readbytes);
	}
	
	conf  = ap_get_module_config(f->c->base_server->module_config,
		&whois_module);

	rv = ap_get_brigade(f->next, b, AP_MODE_GETLINE, APR_BLOCK_READ, 0);
	if (rv != APR_SUCCESS) {
		e = apr_bucket_eos_create(f->c->bucket_alloc);
		APR_BRIGADE_INSERT_TAIL(b, e);
		return ap_pass_brigade(f->c->output_filters, b);
	}

	/* Insert the query prefix in front of the query */	
	e = apr_bucket_immortal_create(conf->whois_prefix, strlen(conf->whois_prefix), f->c->bucket_alloc);
	APR_BRIGADE_INSERT_HEAD(b, e);

	/* read, remove, quote & reinsert the query */
	e = APR_BUCKET_NEXT(e);
	apr_bucket_read(e, &original, &len, APR_BLOCK_READ);
	APR_BUCKET_REMOVE(e);
	crlfpos = strstr(original, "\r\n");
	if (!crlfpos) {
		return DECLINED;
		}
	else {
		memset(crlfpos, 0, 1);
		}
	
	quoted = ap_escape_path_segment(f->c->pool, original);
	e = apr_bucket_immortal_create(quoted, strlen(quoted), f->c->bucket_alloc);
	APR_BRIGADE_INSERT_TAIL(b, e);
	/* reinsert CRLF after query */
	e = apr_bucket_immortal_create("\r\n", strlen("\r\n"), f->c->bucket_alloc);
	APR_BRIGADE_INSERT_TAIL(b, e);
	/* and signal end of HTTP query */
	e = apr_bucket_flush_create(f->c->bucket_alloc);
	APR_BRIGADE_INSERT_TAIL(b, e);
	e = apr_bucket_eos_create(f->c->bucket_alloc);
	APR_BRIGADE_INSERT_TAIL(b, e);
	e = APR_BRIGADE_FIRST(b);

	/* Everything done, proceed to HTTP */
	return OK;
}

	

static int process_whois_connection(conn_rec *c)
{
	whois_conn_rec *conf;
	
	conf  = ap_get_module_config(c->base_server->module_config,
		&whois_module);

	if (!conf->whois_on) 
	{
		return DECLINED;
	}
	
	ap_add_input_filter("WHOIS_IN", NULL, NULL, c);
	return DECLINED;
}


static const command_rec whois_cmds[] =
{
	AP_INIT_FLAG("WhoisProtocol", whois_on, NULL, RSRC_CONF,
		"Enable whois protocol for this host"),
	AP_INIT_TAKE1("WhoisPrefix", whois_prefix, NULL, RSRC_CONF,
		"The URI to which whois requests should be mapped"),
	{ NULL }
};

static void register_hooks(apr_pool_t *p)
{
	ap_register_input_filter("WHOIS_IN", whois_input_filter,
		NULL, AP_FTYPE_CONNECTION);
	ap_hook_process_connection(process_whois_connection, NULL, NULL, 
		APR_HOOK_MIDDLE);
}

module AP_MODULE_DECLARE_DATA whois_module = {
	STANDARD20_MODULE_STUFF,
	NULL,
	NULL,
	whois_create_server,
	NULL,
	whois_cmds,
	register_hooks
};