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

#define ARRLEN(x) (sizeof(x) / sizeof(x[0]))

typedef struct qd_http_request_info_t {
    //char method[20];
    //char scheme[30];
    //char authority[30];
    //char path[200];
    int32_t          stream_id;   // The stream id on every request.
    uint64_t         num_bytes_in; // total bytes in per request
    uint64_t         num_bytes_out; // total bytes out per request.
    vflow_record_t  *vflow;
} qd_http_request_info_t;

//
// Every tcp connection object has a corresponding single qd_http2_po_t object. One to one relationship.
//
typedef struct qd_http2_po_t {
    nghttp2_session           *server_session;
    nghttp2_session           *client_session;
    uint64_t                   num_requests;  // number of requests that came in on a single connection
    vflow_record_t            *connection_vflow; // connection vflow record.
    nghttp2_session_callbacks *callbacks;  // nghttp2 callbacks
} qd_http2_po_t;

ALLOC_DECLARE(qd_http2_po_t);
ALLOC_DEFINE(qd_http2_po_t);

ALLOC_DECLARE(qd_http_request_info_t);
ALLOC_DEFINE(qd_http_request_info_t);

//static void free_qd_request_info(qd_http_request_info_t *request_info, bool on_shutdown)
//{
//    // End the vanflow record for the stream level vanflow.
//    vflow_end_record(request_info->vflow);
//    free_qd_request_info_t(request_info);
//}

static qd_http_request_info_t *get_qd_request_info(qd_http2_po_t *http2_observer, int32_t stream_id)
{
    qd_http_request_info_t *request_info = (qd_http_request_info_t *) nghttp2_session_get_stream_user_data(http2_observer->server_session, stream_id);
    return request_info;
}

static qd_http_request_info_t *create_qd_request_info(qd_http2_po_t *http2_observer, int32_t stream_id)
{
    qd_http_request_info_t *request_info = new_qd_http_request_info_t();
    ZERO(request_info);
    request_info->stream_id = stream_id;

    // Store the request_info object in a hashtable provided by nghttp2 so it can retrieved whenever needed.
    nghttp2_session_set_stream_user_data(http2_observer->server_session, stream_id, request_info);
    //
    // Start a vanflow record for the http2 stream. The parent of this vanflow is
    // its connection's vanflow record.
    //
    request_info->vflow = vflow_start_record(VFLOW_RECORD_FLOW, http2_observer->connection_vflow);
    vflow_set_uint64(request_info->vflow, VFLOW_ATTRIBUTE_OCTETS, 0);
    vflow_add_rate(request_info->vflow, VFLOW_ATTRIBUTE_OCTETS, VFLOW_ATTRIBUTE_OCTET_RATE);

    //
    // Start latency timer for this http2  stream.
    // This stream can be on an ingress connection or an egress connection.
    //
    vflow_latency_start(request_info->vflow);

    return request_info;
}

static int on_begin_headers_callback(nghttp2_session *session,
                                     const nghttp2_frame *frame,
                                     void *user_data)
{
    qd_http2_po_t *http2_observer = (qd_http2_po_t *) user_data;
    http2_observer->num_requests++;
    vflow_set_uint64(http2_observer->connection_vflow, VFLOW_ATTRIBUTE_FLOW_COUNT_L7, http2_observer->num_requests);

//    if (!!conn->common.parent && conn->common.parent->context_type == TL_LISTENER) {
//        qd_tcp_listener_t *listener = (qd_tcp_listener_t*) conn->common.parent;
//
//        //TODO: Add locking around this because listener is shared across connections
//        listener->num_requests++;
//        printf("listener->num_requests=%i\n", (int)listener->num_requests);
//        vflow_set_uint64(listener->common.vflow, VFLOW_ATTRIBUTE_FLOW_COUNT_L7, listener->num_requests);
//    }

    // For the client applications, frame->hd.type is either NGHTTP2_HEADERS or NGHTTP2_PUSH_PROMISE
    // TODO - deal with NGHTTP2_PUSH_PROMISE
    int32_t stream_id = frame->hd.stream_id;
    if (frame->hd.type == NGHTTP2_HEADERS) {
        qd_http_request_info_t *request_info = get_qd_request_info(http2_observer, stream_id);
        if(request_info) {
            // this is a request, create the qd_request_info object for the very first time
            create_qd_request_info(http2_observer, stream_id);
        }
        else {
            // this is a response
        }
    }
    return 0;
}

/**
 * Callback function invoked when a header name/value pair is received for the frame.
 * The name of length namelen is header name. The value of length valuelen is header value.
 */
static int on_header_callback(nghttp2_session *session,
                              const nghttp2_frame *frame,
                              const uint8_t *name,
                              size_t namelen,
                              const uint8_t *value,
                              size_t valuelen,
                              uint8_t flags,
                              void *user_data)
{
    printf("on_header_callback\n");
   // qd_http2_po_t *http2_observer = (qd_http2_po_t *) user_data;
    switch (frame->hd.type) {
        case NGHTTP2_HEADERS: {
            if (strcmp(":method", (const char *)name) == 0) {
                printf("method is %s\n", (char *) value);
                //strncpy(http2_observer->request_info->method, (char *) value, valuelen + 1);
            } else if (strcmp(":scheme", (const char *)name) == 0) {
                printf("scheme is %s\n", (char *) value);
                //strncpy(http2_observer->request_info->scheme, (char *) value, valuelen + 1);
            } else if (strcmp(":authority", (const char *)name) == 0) {
                printf("authority is %s\n", (char *) value);
                //strncpy(http2_observer->request_info->authority, (char *) value, valuelen + 1);
            } else if (strcmp(":path", (const char *)name) == 0) {
                printf("path is %s\n", (char *) value);
                //strncpy(http2_observer->request_info->path, (char *) value, valuelen + 1);
            }
            else {
                printf("something is %s\n", (char *) name);
            }
        }
        break;
        default:
            break;
    }

    return 0;
}

//static int on_frame_recv_callback(nghttp2_session *session,
//                                  const nghttp2_frame *frame,
//                                  void *user_data)
//{
//    qd_http2_po_t *http2_observer = (qd_http2_po_t *) user_data;
//    int32_t stream_id = frame->hd.stream_id;
//    switch (frame->hd.type) {
//    case NGHTTP2_CONTINUATION: {
//        if (frame->hd.flags & NGHTTP2_FLAG_END_HEADERS) {
//            // All headers have arrived.
//            nghttp2_nv nva[] = {
//                  MAKE_NV_LL(":method", "GET"),
//                  MAKE_NV_L(":scheme", req->scheme.iov_base, req->scheme.iov_len),
//                  MAKE_NV_L(":authority", req->authority.iov_base, req->authority.iov_len),
//                  MAKE_NV_L(":path", req->path.iov_base, req->path.iov_len)};
//              int rv;
//              rv = nghttp2_submit_request(conn->ngh2, NULL, nva, ARRLEN(nva), NULL, req);
//                if (rv < 0) {
//                  fprintf(stderr, "error: (nghttp2_submit_requset) %s\n",
//                          nghttp2_strerror(rv));
//                  return -1;
//                }
//        }
//    }
//    break;
//    default:
//        break;
//    }
//}

/**
 * Callback function invoked when library provides the error message intended for human consumption. This callback is solely for debugging purpose.
 * The msg is typically NULL-terminated string of length len. len does not include the sentinel NULL character.
 */
static int on_error_callback(nghttp2_session *session, int lib_error_code, const char *msg, size_t len, void *user_data)
{
    //TODO: Log the error and close the connection.
    return 0;
}

void qdpo_data(qdpo_transport_handle_t transport_handle, bool from_client, qd_buffer_t *buf, size_t offset)
{
    if (!buf)
        return;
    qd_http2_po_t *protocol_observer= (qd_http2_po_t*) transport_handle;

    //
    // nghttp2 does not take ownership of the passed in buf. It is ok to immediately free the buffer after nghttp2_session_mem_recv returns
    // rv is usually equal to buffer size. If rv < 0, there is either an error in the callback code or in the data itself.
    //
    int rv = 0;
    if (from_client) {
        printf("Doing qdpo_data server_session\n");
        rv = nghttp2_session_mem_recv(protocol_observer->server_session, qd_buffer_base(buf), qd_buffer_size(buf));
    }
    else {
        printf("Doing qdpo_data client_session buf size=%i\n", (int)qd_buffer_size(buf));
        rv = nghttp2_session_mem_recv(protocol_observer->client_session, qd_buffer_base(buf), qd_buffer_size(buf));
    }

    if(rv!=0) {
        //TODO: Log error message and possibly close the connection.
    }
}

void qdpo_end(qdpo_transport_handle_t transport_handle)
{
    qd_http2_po_t *protocol_observer= (qd_http2_po_t*) transport_handle;
    nghttp2_session_del(protocol_observer->server_session);
    nghttp2_session_del(protocol_observer->client_session);
    free_qd_http2_po_t(protocol_observer);
}

qdpo_transport_handle_t qdpo_first(qdpo_t *observer, vflow_record_t *vflow, void *transport_context, qd_buffer_t *buf, size_t offset)
{
    //
    // Register necessary nghttp2 callbacks.
    //
    qd_http2_po_t *http2_observer = new_qd_http2_po_t();
    ZERO(http2_observer);
    http2_observer->connection_vflow = vflow;
    nghttp2_session_callbacks_new(&http2_observer->callbacks);

    // this callback is called once on beginning of each request
    nghttp2_session_callbacks_set_on_begin_headers_callback(http2_observer->callbacks, on_begin_headers_callback);

    //callback to be called on each http header
    nghttp2_session_callbacks_set_on_header_callback(http2_observer->callbacks, on_header_callback);

    // This is a general error callback
    nghttp2_session_callbacks_set_error_callback2(http2_observer->callbacks, on_error_callback);
    //nghttp2_session_callbacks_set_on_frame_recv_callback(http2_observer->callbacks, on_frame_recv_callback);

    // Create the nghttp2 server session. This will tell nghttp2 that this session will be used as a server session.
    nghttp2_session_server_new(&(http2_observer->server_session), http2_observer->callbacks, (void *)http2_observer);

    int rv = nghttp2_session_mem_recv(http2_observer->server_session, qd_buffer_base(buf), qd_buffer_size(buf));

    if (rv < 0) {
        //TODO: Log the error, there was a problem with processing the http2 data, the connection needs to be closed.
        return 0;
    }

    nghttp2_option *option;
    nghttp2_option_new(&option);
    nghttp2_option_set_no_recv_client_magic(option, 1);
    nghttp2_option_set_no_http_messaging(option, 1);
    rv = nghttp2_session_server_new2(&http2_observer->client_session, http2_observer->callbacks, (void *)http2_observer, option);

    if (rv != 0) {
        fprintf(stderr, "error: (nghttp2_session_client_new) %s\n", nghttp2_strerror(rv));
        return 0;
    }

    nghttp2_session_callbacks_del(http2_observer->callbacks);
    //nghttp2_settings_entry settings[1];
    //settings[0].settings_id = NGHTTP2_SETTINGS_MAX_CONCURRENT_STREAMS;
    //settings[0].value = 100;

    //rv = nghttp2_submit_settings(http2_observer->client_session, NGHTTP2_FLAG_NONE, settings, ARRLEN(settings));
    //if (rv != 0) {
    //    fprintf(stderr, "error: (nghttp2_submit_settings) %s\n", nghttp2_strerror(rv));
    //    return 0;
    //}


    return http2_observer;
}
