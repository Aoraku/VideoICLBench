import Head from "next/head";
import type { AppProps } from "next/app";
import store from "../redux/store";
import { Provider } from "react-redux";
import "../styles/globals.css";

// eslint-disable-next-line @typescript-eslint/naming-convention
const App = ({ Component, pageProps }: AppProps) => {
    return (
        <>
            <Head>
                <title>VIC IM</title>
            </Head>
            <Component {...pageProps} />
        </>
    );
};

export default function AppWrapper(props: AppProps) {
    return (
        <Provider store={store}>
            <App {...props} />
        </Provider>
    );
}
