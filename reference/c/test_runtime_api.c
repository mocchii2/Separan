#include "separan_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int closed_connections;
static int began_transactions, committed_transactions, rolled_back_transactions;
static char *copy_result(const char *text) {
    size_t length = strlen(text); char *copy = malloc(length + 1);
    if (copy) memcpy(copy, text, length + 1); return copy;
}
static int db_connect(void *context, const char *request, void **connection, char **error) {
    (void)error;
    if (context) return *(int *)context;
    if (!strstr(request, "\"driver\":\"mock\"") || !strstr(request, "\"database\":\"test\"")) return 1;
    *connection = (void *)1; return 0;
}
static int db_call(void *context, void *connection, const char *operation,
                   const char *request, char **result, char **error) {
    (void)context; (void)error;
    if (connection != (void *)1 || !request) return 1;
    const char *json = "null";
    if (!strcmp(operation, "db_query")) json = "[{\"id\":1}]";
    else if (!strcmp(operation, "db_query_one")) json = "{\"id\":1}";
    else if (!strcmp(operation, "db_scalar")) json = "42";
    else if (!strcmp(operation, "db_execute")) json = "1";
    else if (!strcmp(operation, "db_tables")) json = "[\"sample\"]";
    else if (!strcmp(operation, "db_columns")) json = "[{\"name\":\"id\"}]";
    else if (!strcmp(operation, "db_indexes")) json = "[{\"name\":\"sample_pk\"}]";
    else if (!strcmp(operation, "db_primary_key")) json = "{\"columns\":[\"id\"]}";
    else if (!strcmp(operation, "db_server_info")) json = "{\"driver\":\"mock\"}";
    else if (!strcmp(operation, "db_version")) json = "\"1.0\"";
    else if (!strcmp(operation, "db_begin")) began_transactions++;
    else if (!strcmp(operation, "db_commit")) committed_transactions++;
    else if (!strcmp(operation, "db_rollback")) rolled_back_transactions++;
    *result = copy_result(json); return *result ? 0 : 1;
}
static void db_close(void *context, void *connection) {
    (void)context; if (connection == (void *)1) closed_connections++;
}
static unsigned process_calls;
static int process_call(void *context, const char *operation, const char *request,
                        char **result, char **error) {
    (void)error;
    if (context && *(int *)context) return *(int *)context;
    if (!request || !strstr(request, "\"command\":\"mock\"")) return 2;
    if (!strcmp(operation, "command_exists")) {
        process_calls |= 1; *result = copy_result("true");
    } else {
        if ((!strcmp(operation, "exec") || !strcmp(operation, "exec_checked")) &&
            !strstr(request, "\"arguments\":[\"one\"]")) return 2;
        if (!strcmp(operation, "exec")) process_calls |= 2;
        else if (!strcmp(operation, "exec_checked")) process_calls |= 4;
        else if (!strcmp(operation, "shell_exec")) process_calls |= 8;
        else return 2;
        *result = copy_result("{\"exit_code\":0,\"stdout\":\"ok\\n\",\"stderr\":\"\","
                              "\"stdout_bytes\":\"6F6B0A\",\"stderr_bytes\":\"\","
                              "\"timed_out\":false,\"duration\":5,\"command\":\"mock\"}");
    }
    return *result ? 0 : 6;
}
static unsigned host_calls;
static unsigned mail_attachment_calls;
static const char *invalid_host_shape(int shape,const char *operation) {
    if(shape==4&&!strcmp(operation,"http_profile"))return "{\"name\":\"mock\",\"user_agent\":\"test\",\"language\":\"en\",\"accept_encoding\":\"identity\"}";
    if(shape==5&&!strcmp(operation,"basic_auth"))return "{\"kind\":\"basic\",\"name\":\"Authorization\",\"value\":\"token\",\"location\":\"header\"}";
    if(shape==6&&!strcmp(operation,"oauth_client_credentials"))return "{\"access_token\":{\"$bytes\":\"746F6B656E\"},\"token_type\":\"Bearer\",\"expires_in\":-1,\"scope\":\"read\"}";
    if(shape==7&&!strcmp(operation,"cookie_jar"))return "{\"kind\":\"cookie_store\"}";
    if(shape==8&&!strcmp(operation,"mail_create_message"))return "{\"kind\":\"mail_sender\"}";
    if(shape==9&&!strcmp(operation,"mail_create_sender"))return "{\"kind\":\"mail_sender\",\"extra\":true}";
    if(shape==10&&!strcmp(operation,"xml_document_parse"))return "{\"kind\":\"xml_element\"}";
    if(shape==11&&!strcmp(operation,"xml_find"))return "{\"kind\":\"xml_document\"}";
    if(shape==12&&!strcmp(operation,"i2c_open"))return "{\"board\":\"mock\",\"kind\":\"i2c\",\"index\":0,\"pins\":[{\"name\":\"SDA\",\"physical_pin\":1,\"backend_pin\":\"P1\",\"voltage\":\"3.3\",\"capabilities\":[\"i2c\"]}]}";
    if(shape==13&&!strcmp(operation,"network_interface"))return "{\"name\":\"eth0\"}";
    if(shape==14&&!strcmp(operation,"tcp_connect"))return "{\"kind\":\"udp_socket\"}";
    if(shape==15&&!strcmp(operation,"udp_open"))return "{\"kind\":\"tcp_connection\"}";
    if(shape==16&&!strcmp(operation,"dhcp_server_start"))return "{\"kind\":\"dns_server\"}";
    if(shape==17&&!strcmp(operation,"dns_server_start"))return "{\"kind\":\"dhcp_server\"}";
    if(shape==18&&!strcmp(operation,"xml_create_element"))return "{\"kind\":\"xml_document\"}";
    return NULL;
}
static int host_call(void *context, const char *operation, const char *request,
                     char **result, char **error_code, char **error_message) {
    if (context && *(int *)context == 1) {
        *error_code = copy_result("E975"); *error_message = copy_result("host test failure"); return 1;
    }
    if (!request || !strstr(request, "\"arguments\"") || !strstr(request, "\"named\"")) return 1;
    const char *json = "null";
    const char *invalid=context?invalid_host_shape(*(int *)context,operation):NULL;
    if(invalid){*result=copy_result(invalid);return *result?0:1;}
    if (!strcmp(operation, "http_get")) { host_calls |= 1; json = context&&*(int *)context==2?"{\"status\":200}":"{\"status\":200,\"url\":\"https://example.test/\",\"headers\":{},\"bytes\":{\"$bytes\":\"\"},\"text\":null,\"encoding\":null,\"redirects\":[],\"cookies\":{}}"; }
    else if (!strcmp(operation, "secret_get")) { host_calls |= 2; json = "{\"$bytes\":\"736563726574\"}"; }
    else if (!strcmp(operation, "http_profile")) json = "{\"name\":\"mock\",\"user_agent\":\"test\",\"accept\":\"*/*\",\"language\":\"en\",\"accept_encoding\":\"identity\"}";
    else if (!strcmp(operation, "basic_auth")) json = "{\"kind\":\"basic\",\"name\":\"Authorization\",\"value\":{\"$bytes\":\"746F6B656E\"},\"location\":\"header\"}";
    else if (!strcmp(operation, "oauth_client_credentials")) json = "{\"access_token\":{\"$bytes\":\"746F6B656E\"},\"token_type\":\"Bearer\",\"expires_in\":3600,\"scope\":\"read\"}";
    else if (!strcmp(operation, "mail_create_message")) { host_calls |= 4; json = "{\"kind\":\"mail_message\"}"; }
    else if (!strcmp(operation, "mail_create_sender")) json = "{\"kind\":\"mail_sender\"}";
    else if (!strcmp(operation, "mail_add_attachment_bytes")) {
        if(!strstr(request,"\"arguments\":[{\"kind\":\"mail_message\"},\"report.bin\",{\"$bytes\":\"00FF\"},\"application/octet-stream\"]"))return 1;
        mail_attachment_calls|=1;json="null";
    }
    else if (!strcmp(operation, "mail_add_inline_attachment_bytes")) {
        if(!strstr(request,"\"arguments\":[{\"kind\":\"mail_message\"},\"logo.png\",{\"$bytes\":\"89504E47\"},\"image/png\",\"logo\"]"))return 1;
        mail_attachment_calls|=2;json="null";
    }
    else if (!strcmp(operation, "mail_add_attachment")) {
        if(!strstr(request,"\"arguments\":[{\"kind\":\"mail_message\"},\"fixture.txt\"]")||
           !strstr(request,"\"named\":{\"content_type\":\"text/plain\"}"))return 1;
        mail_attachment_calls|=4;json="null";
    }
    else if (!strcmp(operation, "cookie_jar")) { host_calls |= 8; json = "{\"kind\":\"cookie_jar\"}"; }
    else if (!strcmp(operation, "cookie_get")) json = "{\"$bytes\":\"736563726574\"}";
    else if (!strcmp(operation, "xml_document_parse")) json = "{\"kind\":\"xml_document\"}";
    else if (!strcmp(operation, "xml_create_element")) json = "{\"kind\":\"xml_element\"}";
    else if (!strcmp(operation, "xml_find")) json = "{\"kind\":\"xml_element\"}";
    else if (!strcmp(operation, "board_select")) json = context&&*(int *)context==3 ? "{\"id\":\"mock\"}" : "{\"id\":\"mock\",\"name\":\"Mock Board\",\"family\":\"test\",\"cpu\":\"cpu\",\"voltage\":3.3,\"flash_bytes\":1024,\"ram_bytes\":512,\"features\":[\"gpio\"]}";
    else if (!strcmp(operation, "i2c_open")) json = "{\"board\":\"mock\",\"kind\":\"i2c\",\"index\":0,\"pins\":[{\"name\":\"SDA\",\"physical_pin\":1,\"backend_pin\":\"P1\",\"voltage\":3.3,\"capabilities\":[\"i2c\"]}]}";
    else if (!strcmp(operation, "tcp_connect")) json = "{\"kind\":\"tcp_connection\"}";
    else if (!strcmp(operation, "udp_open")) json = "{\"kind\":\"udp_socket\"}";
    else if (!strcmp(operation, "dhcp_server_start")) json = "{\"kind\":\"dhcp_server\"}";
    else if (!strcmp(operation, "dns_server_start")) json = "{\"kind\":\"dns_server\"}";
    else if (!strcmp(operation, "network_interface")) json = "{\"name\":\"eth0\",\"index\":1,\"description\":\"Ethernet\",\"kind\":\"ethernet\",\"connected\":true,\"addresses\":[\"192.0.2.10\"],\"ip_address\":\"192.0.2.10\",\"gateway\":\"192.0.2.1\",\"subnet_mask\":\"255.255.255.0\",\"dns_servers\":[\"192.0.2.53\"],\"mac_address\":\"00:11:22:33:44:55\",\"ssid\":null,\"bssid\":null,\"channel\":null,\"signal_strength\":null,\"address_mode\":\"dhcp\",\"dhcp_status\":\"bound\",\"dhcp_lease\":null,\"link_local_fallback\":false}";
    else if (!strcmp(operation, "network_preferred_interface")) json = "null";
    else if (!strcmp(operation, "network_ip_addresses") || !strcmp(operation, "dns_resolve")) json = "[\"192.0.2.10\"]";
    else if (!strcmp(operation, "request_method")) { host_calls |= 16; json = "\"GET\""; }
    else if (!strcmp(operation, "board_name")) { host_calls |= 32; json = "\"mock-board\""; }
    else if (!strcmp(operation, "network_hostname")) { host_calls |= 64; json = "\"mock-host\""; }
    else if (!strcmp(operation, "dns_server_status")) { host_calls |= 128; json = "{\"running\":true}"; }
    else if (!strcmp(operation, "regex_find")) json = "{\"text\":\"a\",\"start\":0,\"end\":1,\"groups\":[\"a\"]}";
    else if (!strcmp(operation, "regex_match")) json = "true";
    else if (!strcmp(operation, "mail_address")) json = "{\"address\":\"alice@example.test\",\"display_name\":\"Alice\"}";
    else if (!strcmp(operation, "mail_send_message")) json = "{\"provider\":\"mock\",\"message_id\":\"id-1\",\"accepted_recipients\":2}";
    else if (!strcmp(operation, "yaml_to_object")) json = "{\"value\":42}";
    else if (!strcmp(operation, "encrypt_authenticated")) json = "{\"$bytes\":\"00FF\"}";
    else return 1;
    *result = copy_result(json); return *result ? 0 : 1;
}

static int rejects_host_shape(separan_runtime_options *options,separan_host_adapter *host,
                              int shape,const char *source) {
    FILE *output=tmpfile(),*errors=tmpfile();if(!output||!errors){if(output)fclose(output);if(errors)fclose(errors);return 0;}
    host->context=&shape;
    int status=separan_run_source_with_options(source,options,output,errors);
    host->context=NULL;rewind(errors);char line[512];
    int rejected=status!=0&&fgets(line,sizeof(line),errors)&&strstr(line,"E720");
    fclose(output);fclose(errors);return rejected;
}
static int rejects_fixed_member(separan_runtime_options *options,separan_host_adapter *host,
                                const char *source) {
    FILE *output=tmpfile(),*errors=tmpfile();if(!output||!errors){if(output)fclose(output);if(errors)fclose(errors);return 0;}
    host->context=NULL;int status=separan_run_source_with_options(source,options,output,errors);
    rewind(errors);char line[512];int rejected=status!=0&&fgets(line,sizeof(line),errors)&&strstr(line,"E212");
    fclose(output);fclose(errors);return rejected;
}

int main(void) {
    separan_runtime_options restricted = {.root = ".", .read_files = 0,
                                          .write_files = 0, .discover_paths = 0};
    FILE *output = tmpfile(), *errors = tmpfile();
    if (!output || !errors) return 1;
    if (separan_run_source_with_options("print 2 + 3\n", &restricted, output, errors)) return 2;
    rewind(output);
    char line[512];
    if (!fgets(line, sizeof(line), output) || strcmp(line, "5\n")) return 3;
    if (!separan_run_source_with_options("print read_text(\"x.txt\")\n", &restricted, output, errors)) return 4;
    rewind(errors);
    if (!fgets(line, sizeof(line), errors) || !strstr(line, "E720")) return 5;
    FILE *environment_errors = tmpfile();
    if (!environment_errors) return 6;
    if (!separan_run_source_with_options("print env_get(\"PATH\")\n", &restricted, output,
                                         environment_errors)) return 7;
    rewind(environment_errors);
    if (!fgets(line, sizeof(line), environment_errors) || !strstr(line, "E720")) return 8;
    fclose(environment_errors);
    separan_database_adapter database = {.connect = db_connect, .call = db_call, .close = db_close};
    restricted.database = &database;
    FILE *database_output = tmpfile(), *database_errors = tmpfile();
    if (!database_output || !database_errors) return 9;
    const char *database_source =
        "SEP:main\n"
        "db = db_connect(driver = \"mock\", database = \"test\")\n"
        "print type_of(db)\nprint db_scalar(db, \"select 42\", [])\n"
        "print db_execute(db, \"update sample set id = id\", [])\n"
        "print db_query(db, \"select id from sample\", [])[0].id\n"
        "print db_query_one(db, \"select id from sample\", []).id\n"
        "db_begin(db)\ndb_commit(db)\ndb_begin(db)\ndb_rollback(db)\n"
        "transaction db :commit_block\nprint \"transaction\"\nend_transaction:commit_block\n"
        "try :rollback_block\ntransaction db :rollback_transaction\nthrow value_error(\"rollback\")\nend_transaction:rollback_transaction\n"
        "catch value_error :rollback_block\nprint \"rolled back\"\nendtry:rollback_block\n"
        "print db_tables(db)[0]\nprint db_columns(db, \"sample\")[0].name\n"
        "print db_indexes(db, \"sample\")[0].name\n"
        "print db_primary_key(db, \"sample\").columns[0]\n"
        "print db_server_info(db).driver\nprint db_version(db)\n"
        "db_close(db)\nEND_SEP:main\n";
    if (separan_run_source_with_options(database_source, &restricted, database_output, database_errors)) return 10;
    rewind(database_output);
    const char *expected[] = {"db_connection\n","42\n","1\n","1\n","1\n","transaction\n","rolled back\n","sample\n","id\n","sample_pk\n","id\n","mock\n","1.0\n"};
    for (size_t i = 0; i < sizeof(expected)/sizeof(*expected); i++)
        if (!fgets(line, sizeof(line), database_output) || strcmp(line, expected[i])) return 11;
    if (closed_connections != 1) return 12;
    if (began_transactions != 4 || committed_transactions != 2 || rolled_back_transactions != 2) return 12;
    fclose(database_output); fclose(database_errors);
    FILE *db_stress_output=tmpfile(),*db_stress_errors=tmpfile();if(!db_stress_output||!db_stress_errors)return 105;
    const char *db_stress_source="SEP:main\nindex=0\nwhile index<1000 :connections\ndb=db_connect(driver=\"mock\",database=\"test\")\ndb_close(db)\nindex=index+1\nendwhile:connections\nEND_SEP:main\n";
    if(separan_run_source_with_options(db_stress_source,&restricted,db_stress_output,db_stress_errors))return 106;
    if(closed_connections!=1001)return 107;
    fclose(db_stress_output);fclose(db_stress_errors);
    int authentication_error = 3; database.context = &authentication_error;
    FILE *classified_errors = tmpfile(); if (!classified_errors) return 13;
    if (!separan_run_source_with_options("SEP:main\ndb_connect(driver = \"mock\", database = \"test\")\nEND_SEP:main\n",
                                         &restricted, output, classified_errors)) return 14;
    rewind(classified_errors);
    if (!fgets(line, sizeof(line), classified_errors) || !strstr(line, "E902")) {
        fputs(line, stderr); return 15;
    }
    fclose(classified_errors);
    separan_process_adapter process = {.call = process_call}; restricted.process = &process;
    FILE *process_output = tmpfile(), *process_errors = tmpfile();
    if (!process_output || !process_errors) return 16;
    const char *process_source =
        "SEP:main\n"
        "print command_exists(\"mock\")\n"
        "result = exec(\"mock\", [\"one\"], timeout = duration(\"1s\"))\n"
        "print type_of(result)\nprint result.exit_code\nprint result.stdout\n"
        "print hex_encode(result.stdout_bytes)\nprint result.duration\nprint result.command\n"
        "print shell_exec(\"mock\").exit_code\n"
        "print exec_checked(\"mock\", [\"one\"]).exit_code\n"
        "END_SEP:main\n";
    if (separan_run_source_with_options(process_source, &restricted, process_output, process_errors)) return 17;
    rewind(process_output);
    const char *process_expected[] = {"true\n","exec_result\n","0\n","ok\n","\n","6F6B0A\n","5ms\n","mock\n","0\n","0\n"};
    for (size_t i = 0; i < sizeof(process_expected)/sizeof(*process_expected); i++) {
        if (!fgets(line, sizeof(line), process_output) || strcmp(line, process_expected[i])) {
            fprintf(stderr, "process output %zu: expected [%s], got [%s]\n", i,
                    process_expected[i], feof(process_output) ? "<EOF>" : line); return 18;
        }
    }
    if (process_calls != 15) return 19;
    fclose(process_output); fclose(process_errors);
    int command_error = 8; process.context = &command_error;
    FILE *process_classified = tmpfile(); if (!process_classified) return 20;
    if (!separan_run_source_with_options("SEP:main\nexec_checked(\"mock\", [\"one\"])\nEND_SEP:main\n",
                                         &restricted, output, process_classified)) return 21;
    rewind(process_classified);
    if (!fgets(line, sizeof(line), process_classified) || !strstr(line, "E808")) return 22;
    fclose(process_classified);
    int timeout_error = 9; process.context = &timeout_error;
    process_classified = tmpfile(); if (!process_classified) return 23;
    if (!separan_run_source_with_options("SEP:main\nexec(\"mock\", [\"one\"])\nEND_SEP:main\n",
                                         &restricted, output, process_classified)) return 24;
    rewind(process_classified);
    if (!fgets(line, sizeof(line), process_classified) || !strstr(line, "E809")) return 25;
    fclose(process_classified);
    separan_host_adapter host = {.call = host_call}; restricted.host = &host;
    FILE *host_output = tmpfile(), *host_errors = tmpfile(); if (!host_output || !host_errors) return 26;
    const char *host_source =
        "SEP:main\n"
        "response = http_get(\"https://example.test\", timeout = duration(\"1s\"))\nprint type_of(response)\nprint response.status\n"
        "print secret_get(\"token\")\nprint type_of(http_profile(\"mock\"))\nauth = basic_auth(\"user\", \"password\")\nprint type_of(auth)\nprint type_of(auth.value)\ntoken = oauth_client_credentials(\"id\", \"secret\", \"https://token.test\")\nprint type_of(token)\nprint type_of(token.access_token)\n"
        "print type_of(mail_create_message())\njar = cookie_jar()\nprint type_of(jar)\nprint type_of(cookie_get(jar, \"session\"))\ndoc = xml_document_parse(\"<root/>\")\nprint type_of(doc)\nprint type_of(xml_find(doc, \"root\"))\nprint request_method()\n"
        "board = board_select(\"mock\")\nprint type_of(board)\nprint board.cpu\nbus = i2c_open()\nprint type_of(bus)\nprint bus.pins[0].name\ninterface = network_interface(\"eth0\")\nprint type_of(interface)\nprint interface.ip_address\n"
        "print type_of(interface.addresses[0])\nprint type_of(network_ip_addresses(interface)[0])\nprint type_of(network_preferred_interface())\nprint type_of(dns_resolve(\"example.test\")[0])\nprint board_name()\nprint network_hostname()\nprint dns_server_status(jar).running\n"
        "print regex_match(\"abc\", \"a.*\")\nprint yaml_to_object(\"value: 42\").value\n"
        "print hex_encode(encrypt_authenticated(\"data\", hex_decode(\"0000000000000000000000000000000000000000000000000000000000000000\")))\n"
        "END_SEP:main\n";
    if (separan_run_source_with_options(host_source, &restricted, host_output, host_errors)) return 27;
    rewind(host_output);
    const char *host_expected[] = {"http_response\n","200\n","[REDACTED]\n","http_profile\n","http_auth\n","secret\n","oauth_token\n","secret\n","mail_message\n","cookie_jar\n","secret\n","xml_document\n","xml_element\n","GET\n","board\n","cpu\n","embedded_bus\n","SDA\n","network_interface\n","192.0.2.10\n","ip_address\n","ip_address\n","network_interface\n","ip_address\n","mock-board\n","mock-host\n","true\n",
                                   "true\n","42\n","00FF\n"};
    for (size_t i = 0; i < sizeof(host_expected)/sizeof(*host_expected); i++)
        if (!fgets(line, sizeof(line), host_output) || strcmp(line, host_expected[i])) return 28;
    if (host_calls != 255) return 29;
    fclose(host_output); fclose(host_errors);
    FILE *member_errors=tmpfile();if(!member_errors)return 64;
    if(!separan_run_source_with_options("board = board_select(\"mock\")\nprint board.missing\n",&restricted,output,member_errors))return 65;
    rewind(member_errors);if(!fgets(line,sizeof(line),member_errors)||!strstr(line,"E212"))return 66;fclose(member_errors);
    FILE *shape_errors=tmpfile();int malformed_board=3;host.context=&malformed_board;if(!shape_errors)return 67;
    if(!separan_run_source_with_options("print board_select(\"mock\")\n",&restricted,output,shape_errors))return 68;
    rewind(shape_errors);if(!fgets(line,sizeof(line),shape_errors)||!strstr(line,"E720"))return 69;fclose(shape_errors);host.context=NULL;
    int invalid_shape=2;host.context=&invalid_shape;shape_errors=tmpfile();if(!shape_errors)return 58;
    if(!separan_run_source_with_options("print http_get(\"https://example.test\")\n",&restricted,output,shape_errors))return 59;
    rewind(shape_errors);if(!fgets(line,sizeof(line),shape_errors)||!strstr(line,"E720"))return 60;fclose(shape_errors);host.context=NULL;
    const struct {int mode;const char *source;} invalid_shapes[]={
        {4,"SEP:main\nprint http_profile(\"mock\")\nEND_SEP:main\n"},
        {5,"SEP:main\nprint basic_auth(\"user\",\"password\")\nEND_SEP:main\n"},
        {6,"SEP:main\nprint oauth_client_credentials(\"id\",\"secret\",\"https://token.test\")\nEND_SEP:main\n"},
        {7,"SEP:main\nprint cookie_jar()\nEND_SEP:main\n"},
        {8,"SEP:main\nprint mail_create_message()\nEND_SEP:main\n"},
        {9,"SEP:main\nprint mail_create_sender()\nEND_SEP:main\n"},
        {10,"SEP:main\nprint xml_document_parse(\"<root/>\")\nEND_SEP:main\n"},
        {11,"SEP:main\ndoc=xml_document_parse(\"<root/>\")\nprint xml_find(doc,\"root\")\nEND_SEP:main\n"},
        {12,"SEP:main\nprint i2c_open()\nEND_SEP:main\n"},
        {13,"SEP:main\nprint network_interface(\"eth0\")\nEND_SEP:main\n"},
        {14,"SEP:main\nprint tcp_connect(\"example.test\",80)\nEND_SEP:main\n"},
        {15,"SEP:main\nprint udp_open()\nEND_SEP:main\n"},
        {16,"SEP:main\nprint dhcp_server_start(\"interface\")\nEND_SEP:main\n"},
        {17,"SEP:main\nprint dns_server_start(\"interface\")\nEND_SEP:main\n"},
        {18,"SEP:main\nprint xml_create_element(\"root\")\nEND_SEP:main\n"},
    };
    for(size_t i=0;i<sizeof(invalid_shapes)/sizeof(*invalid_shapes);i++)
        if(!rejects_host_shape(&restricted,&host,invalid_shapes[i].mode,invalid_shapes[i].source))return 70+(int)i;
    const char *fixed_shapes_source=
        "SEP:main\nprofile=http_profile(\"mock\")\nprint type_of(profile)\nprint profile.name\nprint profile.accept_encoding\n"
        "auth=basic_auth(\"user\",\"password\")\nprint auth.kind\nprint type_of(auth.value)\n"
        "token=oauth_client_credentials(\"id\",\"secret\",\"https://token.test\")\nprint type_of(token)\nprint token.token_type\nprint type_of(token.access_token)\nprint token.expires_in\nprint token.scope\n"
        "print type_of(cookie_jar())\nprint type_of(mail_create_message())\nprint type_of(mail_create_sender())\n"
        "doc=xml_document_parse(\"<root/>\")\nprint type_of(doc)\nprint type_of(xml_find(doc,\"root\"))\nprint type_of(xml_create_element(\"item\"))\n"
        "board=board_select(\"mock\")\nbus=i2c_open()\nprint type_of(board)\nprint type_of(bus)\nprint type_of(bus.pins[0])\n"
        "interface=network_interface(\"eth0\")\nprint type_of(interface)\nprint type_of(interface.addresses[0])\n"
        "print type_of(tcp_connect(\"example.test\",80))\nprint type_of(udp_open())\nprint type_of(dhcp_server_start(\"interface\"))\nprint type_of(dns_server_start(\"interface\"))\nEND_SEP:main\n";
    FILE *shape_output=tmpfile(),*shape_output_errors=tmpfile();if(!shape_output||!shape_output_errors)return 89;
    if(separan_run_source_with_options(fixed_shapes_source,&restricted,shape_output,shape_output_errors))return 90;rewind(shape_output);
    const char *fixed_shape_expected[]={"http_profile\n","mock\n","identity\n","basic\n","secret\n","oauth_token\n","Bearer\n","secret\n","3600\n","read\n","cookie_jar\n","mail_message\n","mail_sender\n","xml_document\n","xml_element\n","xml_element\n","board\n","embedded_bus\n","pin\n","network_interface\n","ip_address\n","tcp_connection\n","udp_socket\n","dhcp_server\n","dns_server\n"};
    for(size_t i=0;i<sizeof(fixed_shape_expected)/sizeof(*fixed_shape_expected);i++)
        if(!fgets(line,sizeof(line),shape_output)||strcmp(line,fixed_shape_expected[i]))return 91;
    fclose(shape_output);fclose(shape_output_errors);
    const char *invalid_members[]={
        "SEP:main\nprofile=http_profile(\"mock\")\nprint profile.missing\nEND_SEP:main\n",
        "SEP:main\nauth=basic_auth(\"user\",\"password\")\nprint auth.missing\nEND_SEP:main\n",
        "SEP:main\ntoken=oauth_client_credentials(\"id\",\"secret\",\"https://token.test\")\nprint token.missing\nEND_SEP:main\n",
        "SEP:main\nprint cookie_jar().missing\nEND_SEP:main\n",
        "SEP:main\nprint mail_create_message().missing\nEND_SEP:main\n",
        "SEP:main\nprint mail_create_sender().missing\nEND_SEP:main\n",
        "SEP:main\ndoc=xml_document_parse(\"<root/>\")\nprint doc.missing\nEND_SEP:main\n",
        "SEP:main\nprint xml_create_element(\"item\").missing\nEND_SEP:main\n",
        "SEP:main\nbus=i2c_open()\nprint bus.pins[0].missing\nEND_SEP:main\n",
        "SEP:main\ninterface=network_interface(\"eth0\")\nprint interface.missing\nEND_SEP:main\n",
        "SEP:main\nprint tcp_connect(\"example.test\",80).missing\nEND_SEP:main\n",
        "SEP:main\nprint udp_open().missing\nEND_SEP:main\n",
    };
    for(size_t i=0;i<sizeof(invalid_members)/sizeof(*invalid_members);i++)
        if(!rejects_fixed_member(&restricted,&host,invalid_members[i]))return 92+(int)i;
    FILE *regex_output=tmpfile(),*regex_errors=tmpfile();if(!regex_output||!regex_errors)return 52;
    const char *regex_source="SEP:main\nmatch = regex_find(\"(a)\", \"a\")\nprint type_of(match)\nprint match.text\nprint match.start\nprint match.end\nprint match.group(0)\nprint match.group(1)\nEND_SEP:main\n";
    if(separan_run_source_with_options(regex_source,&restricted,regex_output,regex_errors))return 53;rewind(regex_output);
    const char *regex_expected[]={"regex_match_result\n","a\n","0\n","1\n","a\n","a\n"};
    for(size_t i=0;i<sizeof(regex_expected)/sizeof(*regex_expected);i++)if(!fgets(line,sizeof(line),regex_output)||strcmp(line,regex_expected[i]))return 54;
    fclose(regex_output);fclose(regex_errors);
    regex_errors=tmpfile();if(!regex_errors)return 55;
    if(!separan_run_source_with_options("match = regex_find(\"(a)\", \"a\")\nprint match.missing()\n",&restricted,output,regex_errors))return 56;
    rewind(regex_errors);if(!fgets(line,sizeof(line),regex_errors)||!strstr(line,"E213"))return 57;fclose(regex_errors);
    FILE *mail_output=tmpfile(),*mail_errors=tmpfile();if(!mail_output||!mail_errors)return 61;
    const char *mail_shape_source="SEP:main\naddress = mail_address(\"alice@example.test\")\nprint type_of(address)\nprint address.address\nprint address.display_name\nresult = mail_send_message(mail_create_sender(), mail_create_message())\nprint type_of(result)\nprint result.provider\nprint result.message_id\nprint result.accepted_recipients\nEND_SEP:main\n";
    if(separan_run_source_with_options(mail_shape_source,&restricted,mail_output,mail_errors))return 62;rewind(mail_output);
    const char *mail_shape_expected[]={"mail_address\n","alice@example.test\n","Alice\n","mail_send_result\n","mock\n","id-1\n","2\n"};
    for(size_t i=0;i<sizeof(mail_shape_expected)/sizeof(*mail_shape_expected);i++)if(!fgets(line,sizeof(line),mail_output)||strcmp(line,mail_shape_expected[i]))return 63;
    fclose(mail_output);fclose(mail_errors);
    FILE *attachment_output=tmpfile(),*attachment_errors=tmpfile();if(!attachment_output||!attachment_errors)return 93;
    const char *attachment_source="SEP:main\nmessage=mail_create_message()\nmail_add_attachment_bytes(message,\"report.bin\",hex_decode(\"00FF\"),\"application/octet-stream\")\nmail_add_inline_attachment_bytes(message,\"logo.png\",hex_decode(\"89504E47\"),\"image/png\",\"logo\")\nmail_add_attachment(message,\"fixture.txt\",content_type=\"text/plain\")\nEND_SEP:main\n";
    if(separan_run_source_with_options(attachment_source,&restricted,attachment_output,attachment_errors))return 94;
    if(mail_attachment_calls!=7)return 95;
    fclose(attachment_output);fclose(attachment_errors);
    int host_error = 1; host.context = &host_error;
    FILE *host_classified = tmpfile(); if (!host_classified) return 30;
    if (!separan_run_source_with_options("SEP:main\nnetwork_hostname()\nEND_SEP:main\n",
                                         &restricted, output, host_classified)) return 31;
    rewind(host_classified);
    if (!fgets(line, sizeof(line), host_classified) || !strstr(line, "E975") || !strstr(line, "host test failure")) return 32;
    fclose(host_classified);
    process.context = &command_error;
    FILE *caught_output = tmpfile(), *caught_errors = tmpfile(); if (!caught_output || !caught_errors) return 33;
    const char *caught_source =
        "SEP:main\n"
        "try :database\ndb_connect(driver = \"mock\", database = \"test\")\n"
        "catch db_auth_error :database\nprint \"database caught\"\nendtry:database\n"
        "try :process\nexec_checked(\"mock\", [\"one\"])\n"
        "catch command_error :process\nprint \"process caught\"\nendtry:process\n"
        "try :network\nnetwork_hostname()\n"
        "catch network_error :network\nprint \"host caught\"\nendtry:network\n"
        "END_SEP:main\n";
    if (separan_run_source_with_options(caught_source, &restricted, caught_output, caught_errors)) return 34;
    rewind(caught_output);
    const char *caught_expected[] = {"database caught\n","process caught\n","host caught\n"};
    for (size_t i = 0; i < sizeof(caught_expected)/sizeof(*caught_expected); i++)
        if (!fgets(line, sizeof(line), caught_output) || strcmp(line, caught_expected[i])) return 35;
    rewind(caught_errors); if (fgets(line, sizeof(line), caught_errors)) return 36;
    fclose(caught_output); fclose(caught_errors);

    separan_runtime *retained = NULL; char *json_result = NULL;
    const char *retained_source =
        "SEP:add(a: number, b: number)\nreturn a + b\nEND_SEP:add\n"
        "SEP:list_size(values)\nreturn length(values)\nEND_SEP:list_size\n"
        "SEP:object_size(value)\nreturn length(object_keys(value))\nEND_SEP:object_size\n";
    if (separan_runtime_create(retained_source, &restricted, output, errors, &retained)) return 37;
    if (separan_runtime_invoke_json(retained, "add", "[20,22]", &json_result) ||
        !json_result || strcmp(json_result, "42")) return 38;
    separan_runtime_release_string(json_result); separan_runtime_destroy(retained);

    const char *diagnostic_source =
        "SEP:divide(value: number)\nreturn value / 0\nEND_SEP:divide\n";
    retained = NULL;
    if (separan_runtime_create(diagnostic_source, &restricted, output, errors, &retained)) return 120;
    if (!separan_runtime_invoke_json(retained, "divide", "[1]", &json_result)) return 121;
    separan_runtime_diagnostic runtime_diagnostic;
    separan_runtime_get_diagnostic(retained, &runtime_diagnostic);
    if (strcmp(runtime_diagnostic.category, "Division by zero") != 0 ||
        strcmp(runtime_diagnostic.description, "Operator '/' cannot use zero as its right operand.") != 0 ||
        strcmp(runtime_diagnostic.actual, "0") != 0 || runtime_diagnostic.line_number != 2 ||
        runtime_diagnostic.column_number != 14) return 122;
    separan_runtime_destroy(retained);

    retained=NULL;
    if(separan_runtime_create(retained_source,&restricted,output,errors,&retained))return 96;
    for(int index=0;index<1000;index++){
        char arguments_json[64],expected_json[32];
        snprintf(arguments_json,sizeof(arguments_json),"[%d,42]",index);
        snprintf(expected_json,sizeof(expected_json),"%d",index+42);
        if(separan_runtime_invoke_json(retained,"add",arguments_json,&json_result)||
           !json_result||strcmp(json_result,expected_json))return 97;
        separan_runtime_release_string(json_result);json_result=NULL;
    }
    const int large_list_count=4096,large_object_count=1024;
    size_t list_capacity=(size_t)large_list_count*8+4,list_length=0;
    char *list_arguments=malloc(list_capacity);if(!list_arguments)return 99;
    list_arguments[list_length++]='[';list_arguments[list_length++]='[';
    for(int index=0;index<large_list_count;index++){
        int written=snprintf(list_arguments+list_length,list_capacity-list_length,
                             "%s%d",index?",":"",index);
        if(written<0||(size_t)written>=list_capacity-list_length)return 100;
        list_length+=(size_t)written;
    }
    list_arguments[list_length++]=']';list_arguments[list_length++]=']';list_arguments[list_length]=0;
    size_t object_capacity=(size_t)large_object_count*24+4,object_length=0;
    char *object_arguments=malloc(object_capacity);if(!object_arguments){free(list_arguments);return 101;}
    object_arguments[object_length++]='[';object_arguments[object_length++]='{';
    for(int index=0;index<large_object_count;index++){
        int written=snprintf(object_arguments+object_length,object_capacity-object_length,
                             "%s\"k%04d\":%d",index?",":"",index,index);
        if(written<0||(size_t)written>=object_capacity-object_length)return 102;
        object_length+=(size_t)written;
    }
    object_arguments[object_length++]='}';object_arguments[object_length++]=']';object_arguments[object_length]=0;
    for(int iteration=0;iteration<50;iteration++){
        if(separan_runtime_invoke_json(retained,"list_size",list_arguments,&json_result)||
           !json_result||strcmp(json_result,"4096"))return 103;
        separan_runtime_release_string(json_result);json_result=NULL;
        if(separan_runtime_invoke_json(retained,"object_size",object_arguments,&json_result)||
           !json_result||strcmp(json_result,"1024"))return 104;
        separan_runtime_release_string(json_result);json_result=NULL;
    }
    free(list_arguments);free(object_arguments);
    separan_runtime_destroy(retained);

    const char *route_source =
        "http_route GET \"/user/:id\" :user\n"
        "http_set_cookie(\"session\", \"abc\", secure = true)\n"
        "return_http(status = 200, content_type = \"text/plain\", body = request_method() + \" \" + request_param(\"id\") + \" \" + request_query(\"view\"))\n"
        "end_http_route:user\n"
        "http_route POST \"/login\" :login\nreturn_http(status = 201, body = request_body())\nend_http_route:login\n"
        "http_route GET \"/old\" :old\nredirect_http(\"/new\", status = 308)\nend_http_route:old\n";
    retained = NULL; restricted.host = NULL;
    if (separan_runtime_create(route_source, &restricted, output, errors, &retained)) return 39;
    if (separan_runtime_dispatch_http_json(retained,
        "{\"method\":\"GET\",\"path\":\"/user/42\",\"query\":{\"view\":[\"full\"]},\"headers\":{\"cookie\":\"session=old\"}}",
        &json_result)) return 40;
    if (!strstr(json_result, "\"status\":200") || !strstr(json_result, "GET 42 full") ||
        !strstr(json_result, "session=abc; Path=/; Secure; HttpOnly; SameSite=Lax")) return 41;
    separan_runtime_release_string(json_result);
    if (separan_runtime_dispatch_http_json(retained,
        "{\"method\":\"HEAD\",\"path\":\"/user/7\",\"query\":{\"view\":[\"brief\"]}}", &json_result) ||
        !strstr(json_result, "\"status\":200") || !strstr(json_result, "HEAD 7 brief")) return 42;
    separan_runtime_release_string(json_result);
    if (separan_runtime_dispatch_http_json(retained,
        "{\"method\":\"POST\",\"path\":\"/login\",\"body\":\"hello\"}", &json_result) ||
        !strstr(json_result, "\"status\":201") || !strstr(json_result, "\"body\":\"hello\"")) return 43;
    separan_runtime_release_string(json_result);
    if (separan_runtime_dispatch_http_json(retained,
        "{\"method\":\"POST\",\"path\":\"/login\",\"body\":{\"$bytes\":\"E697A5\"}}", &json_result) ||
        !strstr(json_result, "\"status\":201") || !strstr(json_result, "\"body\":\"日\"")) return 43;
    separan_runtime_release_string(json_result);
    if (separan_runtime_dispatch_http_json(retained,
        "{\"method\":\"GET\",\"path\":\"/old\"}", &json_result) ||
        !strstr(json_result, "\"status\":308") || !strstr(json_result, "\"Location\":\"/new\"")) return 44;
    separan_runtime_release_string(json_result);
    if (separan_runtime_dispatch_http_json(retained,
        "{\"method\":\"GET\",\"path\":\"/missing\"}", &json_result) ||
        !strstr(json_result, "\"status\":404")) return 45;
    separan_runtime_release_string(json_result);json_result=NULL;
    for(int index=0;index<500;index++){
        char request_json[160],expected_body[64];
        snprintf(request_json,sizeof(request_json),"{\"method\":\"GET\",\"path\":\"/user/%d\",\"query\":{\"view\":[\"full\"]}}",index);
        snprintf(expected_body,sizeof(expected_body),"GET %d full",index);
        if(separan_runtime_dispatch_http_json(retained,request_json,&json_result)||
           !json_result||!strstr(json_result,expected_body))return 98;
        separan_runtime_release_string(json_result);json_result=NULL;
    }
    separan_runtime_destroy(retained);
    FILE *check_errors = tmpfile(); if (!check_errors) return 46;
    if (separan_check_source("value = network_hostname()\nSEP:main\nEND_SEP:main\n", check_errors)) return 47;
    if (!separan_check_source("SEP:main\nprint (1 + )\nEND_SEP:main\n", check_errors)) return 48;
    fclose(check_errors);
    FILE *big_output=tmpfile(),*big_errors=tmpfile();if(!big_output||!big_errors)return 49;
    const char *big_source="SEP:main\nprint 9223372036854775807 + 1\nprint 2 ** 100\nprint -10000000000000000000 // 3\nprint -10000000000000000000 % 3\nprint json_encode(json_decode(\"10000000000000000000\"))\nprint factorial(100)\nEND_SEP:main\n";
    if(separan_run_source(big_source,big_output,big_errors))return 50;rewind(big_output);
    const char *big_expected[]={"9223372036854775808\n","1267650600228229401496703205376\n","-3333333333333333334\n","2\n","10000000000000000000\n","93326215443944152681699238856266700490715968264381621468592963895217599993229915608941463976156518286253697920827223758251185210916864000000000000000000000000\n"};
    for(size_t i=0;i<sizeof(big_expected)/sizeof(*big_expected);i++)if(!fgets(line,sizeof(line),big_output)||strcmp(line,big_expected[i]))return 51;
    fclose(big_output);fclose(big_errors);
    fclose(output); fclose(errors);
    puts("runtime_api: ok");
    return 0;
}
