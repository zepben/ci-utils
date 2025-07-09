/*
 * Copyright 2021 Zeppelin Bend Pty Ltd
 *
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import React, {FunctionComponent} from "react";

import Layout from "@theme/Layout";

import clsx from "clsx";
import styles from "./styles.module.css";
import groupBy from "lodash/groupBy";
import Link from '@docusaurus/Link';

type Item = {
    title: string;
    description: string;
    siteRelUrl?: string;
    type: string;
};

type Props = {
    title: string;
    description: string;
    items: Item[];
};

const Ui: FunctionComponent<Props> = ({title, description, items}) => {
    const groupedByType = groupBy(items, (i) => i.type);

    return (
        <main className="container margin-vert--lg">
            {Object.entries(groupedByType).map(
                ([type, items]: [string, Item[]]) => {
                    return (
                        <>
                            <div className="text--center margin-bottom--md margin-top--md">
                                <h1>{type}</h1>
                            </div>
                            <div className="row">
                                {items.map((t) => (
                                    <div key={t.title} className="col col--6 margin-bottom--lg">
                                        <div className={clsx("card", styles.showcaseItem)}>
                                            <div className="card__body">
                                                <div className="avatar">
                                                    <div className="avatar__intro margin-left--none">
                                                        <h4 className="avatar__name">{t.title}</h4>
                                                        <small className="avatar__subtitle">
                                                            {t.description}
                                                        </small>
                                                    </div>
                                                </div>
                                            </div>
                                            {
                                                <div className="card__footer">
                                                    <div className="button-group button-group--block">
                                                        <Link to={t.siteRelUrl}>Documentation</Link>
                                                    </div>
                                                </div>
                                            }
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </>
                    );
                }
            )}
        </main>
    );
};

export default Ui;
