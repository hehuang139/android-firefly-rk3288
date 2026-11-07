// SPDX-License-Identifier: Apache-2.0
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <cstdio>
#include <cstdint>
#include <cstring>

int main() {
    int fd=open("/dev/dri/card0", O_RDONLY|O_CLOEXEC);
    if(fd<0) {perror("open");return 1;}
    drmModeRes *r=drmModeGetResources(fd);
    if(!r){perror("resources");close(fd);return 2;}
    for(int i=0;i<r->count_connectors;i++) {
        drmModeConnector *c=drmModeGetConnector(fd,r->connectors[i]);
        if(!c)continue;
        printf("connector id=%u connection=%u modes=%d\n",c->connector_id,c->connection,c->count_modes);
        for(int n=0;n<c->count_modes;n++) {
            const auto &m=c->modes[n];
            printf("connector_mode index=%d name=%s clock_khz=%u htotal=%u vtotal=%u flags=0x%x hz=%.9f\n",n,m.name,m.clock,m.htotal,m.vtotal,m.flags,double(m.clock)*1000.0/(m.htotal*m.vtotal));
        }
        drmModeFreeConnector(c);
    }
    drmSetClientCap(fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1);
    drmModePlaneRes *planes=drmModeGetPlaneResources(fd);
    if(planes) {
        for(uint32_t i=0;i<planes->count_planes;i++) {
            drmModePlane *p=drmModeGetPlane(fd,planes->planes[i]);
            if(!p)continue;
            printf("plane id=%u possible_crtcs=0x%x formats=",p->plane_id,p->possible_crtcs);
            for(uint32_t j=0;j<p->count_formats;j++)printf("%c%c%c%c ",p->formats[j]&0xff,(p->formats[j]>>8)&0xff,(p->formats[j]>>16)&0xff,(p->formats[j]>>24)&0xff);
            printf("\n");
            drmModeFreePlane(p);
        }
        drmModeFreePlaneResources(planes);
    }
    int active=-1;
    for(int i=0;i<r->count_crtcs;i++) {
        drmModeCrtc *c=drmModeGetCrtc(fd,r->crtcs[i]);
        if(!c)continue;
        printf("crtc index=%d id=%u mode_valid=%d buffer=%u\n",i,c->crtc_id,c->mode_valid,c->buffer_id);
        if(c->mode_valid){
            const auto &m=c->mode;
            printf("mode name=%s clock_khz=%u hdisplay=%u htotal=%u vdisplay=%u vtotal=%u flags=0x%x expected_hz=%.9f\n",m.name,m.clock,m.hdisplay,m.htotal,m.vdisplay,m.vtotal,m.flags,double(m.clock)*1000.0/(m.htotal*m.vtotal));
            if(active<0)active=i;
        }
        drmModeFreeCrtc(c);
    }
    drmModeFreeResources(r);
    if(active<0){puts("no active crtc");close(fd);return 3;}
    int64_t previous=0;
    for(int i=0;i<121;i++){
        drmVBlank b{};
        b.request.type=static_cast<drmVBlankSeqType>(DRM_VBLANK_RELATIVE | ((active<<DRM_VBLANK_HIGH_CRTC_SHIFT)&DRM_VBLANK_HIGH_CRTC_MASK));
        b.request.sequence=1;
        int result=drmWaitVBlank(fd,&b);
        if(result){printf("vblank_error=%d errno=%d text=%s\n",result,errno,strerror(errno));close(fd);return 4;}
        int64_t ns=int64_t(b.reply.tval_sec)*1000000000LL+int64_t(b.reply.tval_usec)*1000;
        printf("sample=%d seq=%u timestamp_ns=%lld delta_ns=%lld\n",i,b.reply.sequence,static_cast<long long>(ns),static_cast<long long>(previous?ns-previous:0));
        previous=ns;
    }
    close(fd);
    return 0;
}
