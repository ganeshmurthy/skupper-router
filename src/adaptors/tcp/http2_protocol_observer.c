/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

#include <nghttp2/nghttp2.h>

#include <qpid/dispatch/alloc_pool.h>
#include <qpid/dispatch/protocol_observer.h>

#include "tcp_adaptor.h"

const int32_t OBS_WINDOW_SIZE = 65536;
const int32_t OBS_MAX_FRAME_SIZE = 16384;
#define ARRLEN(x) (sizeof(x) / sizeof(x[0]))

nghttp2_session_callbacks *callbacks;

struct qd_http2_po_t {
    qdpo_t     common;
    nghttp2_session           *client_session;
    uint64_t                  requests;

};

ALLOC_DECLARE(qd_http2_po_t);
ALLOC_DEFINE(qd_http2_po_t);

static int on_begin_headers_callback(nghttp2_session *session,
                                     const nghttp2_frame *frame,
                                     void *user_data)
{
    qd_tcp_listener_t *li = (qd_tcp_listener_t*) user_data;
    li->num_requests++;
    printf("li->num_requests=%i\n", (int)li->num_requests);
    printf("on_begin_headers_callback\n");

    // For the client applications, frame->hd.type is either NGHTTP2_HEADERS or NGHTTP2_PUSH_PROMISE
    // TODO - deal with NGHTTP2_PUSH_PROMISE
    if (frame->hd.type == NGHTTP2_HEADERS) {
        if(frame->headers.cat == NGHTTP2_HCAT_REQUEST) {
            int32_t stream_id = frame->hd.stream_id;
            printf("stream_id=%i\n", (int)stream_id);
        }
    }
    return 0;
}

static int on_header_callback(nghttp2_session *session,
                              const nghttp2_frame *frame,
                              const uint8_t *name,
                              size_t namelen,
                              const uint8_t *value,
                              size_t valuelen,
                              uint8_t flags,
                              void *user_data)
{
    //int32_t stream_id = frame->hd.stream_id;

    switch (frame->hd.type) {
        case NGHTTP2_HEADERS: {
            if (strcmp(":method", (const char *)name) == 0) {
                printf ("METHOD is %s\n", (char *)value);
            } else if (strcmp(":status", (const char *)name) == 0) {
                printf ("STATUS is %s\n", (char *)value);
            }
        }
        break;
        default:
            break;
    }

    return 0;
}

static int on_error_callback(nghttp2_session *session, int lib_error_code, const char *msg, size_t len, void *user_data)
{
    return 0;
}

static void http2_connection_init(void  *context) {
    qd_tcp_connection_t *conn = (qd_tcp_connection_t *)context;
    if (!!conn->common.parent && conn->common.parent->context_type == TL_LISTENER) {
        qd_tcp_listener_t *li = (qd_tcp_listener_t*) conn->common.parent;
        nghttp2_session_server_new(&(conn->server_session), callbacks, (void *)li);
        printf("http2_connection_init calling nghttp2_session_server_new conn->server_session=%p\n", (void *)conn->server_session);
    }
}

static void http2_connection_final(void *context) {
    qd_tcp_connection_t *conn = (qd_tcp_connection_t *)context;
    if (!!conn->common.parent && conn->common.parent->context_type == TL_LISTENER) {
        nghttp2_session_del(conn->server_session);
        conn->server_session = 0;
    }
}

static void http2_observe_data(void               *context,
                               unsigned char      *buf,
                               size_t              buf_size,
                               bool                request)
{
    if (!buf || buf_size == 0)
        return;
    qd_tcp_connection_t *conn = (qd_tcp_connection_t*) context;
    int rv=0;

    if (request) {
        printf("http2_observe_data request buf_size=%zu\n", buf_size);
        rv = nghttp2_session_mem_recv2(conn->server_session, buf, buf_size);
    } else {
        //rv = nghttp2_session_mem_recv2(protocol_observer->client_session, buf, buf_size);
        //printf("http2_observe_data response session  is %p\n", (void *)protocol_observer->client_session);
    }

    printf("http2_observe_data rv=%i\n", rv);
}

static int send_data_callback(nghttp2_session *session,
                             nghttp2_frame *frame,
                             const uint8_t *framehd,
                             size_t length,
                             nghttp2_data_source *source,
                             void *user_data) {
    printf("send_data_callback\n");
    return 0;
}

static ssize_t send_callback(nghttp2_session *session,
                             const uint8_t *data,
                             size_t length,
                             int flags,
                             void *user_data) {
    printf("Session in send_callback is %p\n", (void *)session);
    return length;
}

//static void create_settings_frame(qd_tcp_listener_t *listener, nghttp2_session        *session)
//{
//    nghttp2_settings_entry iv[4] = {{NGHTTP2_SETTINGS_MAX_CONCURRENT_STREAMS, 100},
//                                    {NGHTTP2_SETTINGS_INITIAL_WINDOW_SIZE, OBS_WINDOW_SIZE},
//                                    {NGHTTP2_SETTINGS_MAX_FRAME_SIZE, OBS_MAX_FRAME_SIZE},
//                                    {NGHTTP2_SETTINGS_ENABLE_PUSH, 0}};
//
//    // You must call nghttp2_session_send after calling nghttp2_submit_settings
//    int rv = nghttp2_submit_settings(session, NGHTTP2_FLAG_NONE, iv, ARRLEN(iv));
//    if (rv != 0) {
//        return;
//    }
//
//    nghttp2_session_send(session);
//}

qdpo_t *qd_http2_protocol_observer(void *context)
{
    qd_http2_po_t *protocol_observer = new_qd_http2_po_t();
    ZERO(protocol_observer);
    //
    // Register necessary nghttp2 callbacks.
    //
    nghttp2_session_callbacks_new(&callbacks);

    // this callback is called once on beginning of each request
    nghttp2_session_callbacks_set_on_begin_headers_callback(callbacks, on_begin_headers_callback);

    //callback to be called on each http header
    nghttp2_session_callbacks_set_on_header_callback(callbacks, on_header_callback);

    // This is a general error callback
    nghttp2_session_callbacks_set_error_callback2(callbacks, on_error_callback);

    nghttp2_session_callbacks_set_send_callback(callbacks, send_callback);
    nghttp2_session_callbacks_set_send_data_callback(callbacks, send_data_callback);

    //http2_protocol_observer->callbacks = callbacks;

    qdpo_t *common = (qdpo_t *)protocol_observer;
    common->observe = http2_observe_data;
    common->connection_init = http2_connection_init;
    common->connection_final = http2_connection_final;
    //nghttp2_session_callbacks_del(callbacks);
    return (qdpo_t *)protocol_observer;
}

