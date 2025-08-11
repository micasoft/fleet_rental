import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    many2ManyBinaryField,
    Many2ManyBinaryField,
} from "@web/views/fields/many2many_binary/many2many_binary_field";

export class FleetRentalAttachmentPreview extends Many2ManyBinaryField {
    static template = "fleet_rental.attachment_preview";

    getUrl(id) {
        return "/web/content/" + id;
    }

    isImage(ext) {
        return ['jpeg', 'jpg'].includes(ext);
    }

}

export const mailComposerAttachmentList = {
    ...many2ManyBinaryField,
    component: FleetRentalAttachmentPreview,
};

registry.category("fields").add("fleet_rental_attachment_preview", mailComposerAttachmentList);