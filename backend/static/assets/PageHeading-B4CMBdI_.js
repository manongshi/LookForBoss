import{c as u,_ as h,M as k,u as m,b as t,d as o,g as n,t as i,h as e,q as c,x as d,i as g,a1 as b}from"./index-FnI_yIO-.js";/**
 * @license lucide-vue-next v0.468.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const y=u("LoaderCircleIcon",[["path",{d:"M21 12a9 9 0 1 1-6.219-8.56",key:"13zald"}]]);/**
 * @license lucide-vue-next v0.468.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const f=u("SquareIcon",[["rect",{width:"18",height:"18",x:"3",y:"3",rx:"2",key:"afitv7"}]]),v={class:"page-heading"},x={key:0},C={class:"heading-actions"},S=["disabled"],B={__name:"PageHeading",setup(I){const s=k(),{isActive:l,busy:a,interruptCollection:p}=m();return(_,r)=>(t(),o("div",v,[n("div",null,[n("h1",null,i(e(s).meta.title),1),e(s).meta.description?(t(),o("p",x,i(e(s).meta.description),1)):c("",!0)]),n("div",C,[e(l)&&e(s).name!=="workbench"?(t(),o("button",{key:0,class:"button button-white",disabled:e(a).interrupt,onClick:r[0]||(r[0]=L=>e(p)())},[e(a).interrupt?(t(),d(e(y),{key:0,size:15,class:"spin"})):(t(),d(e(f),{key:1,size:13})),g(i(e(a).interrupt?"正在中断":"中断任务"),1)],8,S)):c("",!0),b(_.$slots,"default",{},void 0,!0)])]))}},w=h(B,[["__scopeId","data-v-7dbf2494"]]);export{y as L,w as P,f as S};
